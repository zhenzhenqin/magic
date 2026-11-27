import asyncio
from decimal import Decimal
from secrets import token_urlsafe
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import update

from app.models.ai import AiJob
from tests.ai_benchmark import live_pause_reason, run_cases
from tests.test_ai_jobs import JOBS, attempts, env, new_job, photo, worker
from tests.test_identity import bearer, signed_in
from tests.test_phase41 import qwen_settings, spent


@pytest.mark.parametrize("replacement", [
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
])
def test_endpoint_change_blocks_queued_tasks_before_provider_use(env, replacement):
    app, client = env
    settings = qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    original = new_job(client, auth, [image]).json()
    settings.ai_base_url = replacement
    assert not asyncio.run(worker(app).process_once())
    result = client.get(JOBS + "/" + original["id"], headers=auth).json()
    assert result["error_code"] == "ai_configuration_changed" and not result["can_retry"]
    assert spent(app) == 0 and not attempts(app, original["id"])
    replacement_job = new_job(client, auth, [image]).json()
    assert asyncio.run(worker(app).process_once())
    assert client.get(JOBS + "/" + replacement_job["id"], headers=auth).json()["status"] == "succeeded"


def test_endpoint_change_after_claim_releases_reservation_without_dispatch(env):
    app, client = env
    settings = qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)]).json()["id"]
    service = worker(app)
    claim = service.claim()
    prepared = service.photos(claim)
    settings.ai_base_url = "https://another-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    assert not service.dispatch(claim, prepared)
    assert [(entry.status, entry.error_code) for entry in attempts(app, identifier)] == [
        ("not_sent", "ai_configuration_changed"),
    ]
    assert spent(app) == 0


def test_secret_rotation_keeps_endpoint_binding_and_does_not_expose_fingerprint(env):
    app, client = env
    settings = qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    created = new_job(client, auth, [photo(client, auth)]).json()
    settings.ai_api_key = SecretStr(token_urlsafe(45))
    assert "processing_fingerprint" not in created
    assert asyncio.run(worker(app).process_once())
    view = client.get(JOBS + "/" + created["id"], headers=auth).json()
    assert view["status"] == "succeeded" and "processing_fingerprint" not in view


def test_unbound_legacy_job_is_retained_but_cannot_send(env):
    app, client = env
    qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)]).json()["id"]
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).where(AiJob.id == identifier).values(processing_fingerprint=None))
    assert not asyncio.run(worker(app).process_once())
    result = client.get(JOBS + "/" + identifier, headers=auth).json()
    assert result["error_code"] == "ai_configuration_changed" and result["id"] == identifier
    assert spent(app) == 0


def test_key_and_model_alone_do_not_enable_paid_attempts(env):
    app, client = env
    default_limit = app.state.settings.ai_qwen_cumulative_limit
    qwen_settings(app, default_limit)
    auth = bearer(signed_in(client))
    assert default_limit == 0
    response = new_job(client, auth, [photo(client, auth)])
    assert response.status_code == 429 and response.json()["error"]["code"] == "ai_cumulative_limit"
    assert spent(app) == 0


@pytest.mark.parametrize(("row", "expected"), [
    ({"json_valid": "否"}, "技术"),
    ({"json_valid": "是", "result_status": "recognized"}, "异常"),
    ({"json_valid": "是", "result_status": "no_food", "usage_known": False}, "未知"),
    ({"json_valid": "是", "result_status": "no_food", "usage_known": True, "estimate_amount": Decimal(0)}, ""),
])
def test_live_batch_stop_gate(row, expected):
    reason = live_pause_reason({"status": ["no_food"]}, row, False)
    assert (expected in reason) if expected else reason == ""


def test_batch_records_failure_then_stops_before_next_paid_case(env):
    app, client = env
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)]).json()["id"]
    recorded = {"id": identifier, "status": "failed", "error_code": "ai_provider_auth",
                "worker_online": True, "result": None}
    cases = [{"case": label, "focus": "fixture", "photos": [], "status": ["recognized"], "foods": []}
             for label in ("first", "next")]

    class FixtureAPI:
        def __init__(self):
            self.submissions = 0

        def send(self, method, path):
            data = {"available": True, "worker_online": True, "simulated": False, "consent_version": "sample"}
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)

        def create_job(self, photos, consent):
            self.submissions += 1
            return recorded

    class Ledger:
        def execute(self, *_):
            return SimpleNamespace(fetchall=lambda: [])

    api = FixtureAPI()
    args = SimpleNamespace(run_local="qwen", region="cn-beijing", approved_budget=Decimal(1))
    budget = SimpleNamespace(ledger_estimate=lambda _: SimpleNamespace(amount=Decimal(0)),
                             require_next=lambda *_: None, approved_amount=Decimal(1))
    rows = list(run_cases(api, Ledger(), cases, args, budget, cumulative_limit=3))
    assert api.submissions == 1 and len(rows) == 1
    assert rows[0]["job_id"] == identifier and rows[0]["pause_reason"]
