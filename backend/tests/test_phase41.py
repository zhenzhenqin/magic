import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import MetaData, Table, delete, select, update

from app.core.config import Settings
from app.core.database import utcnow
from app.main import create_app
from app.models.ai import AiCallBudget, AiJob, AiJobMedia, AiUsageLog, AiWorkerHeartbeat
from app.models import User
from app.models.diary import MediaAsset
from app.services.ai_provider import ProviderError
from app.services.ai_prompt import CONSENT_VERSION, PROMPT_VERSION
from tests.ai_benchmark import compare, dataset, spreadsheet_row
from tests.test_ai_jobs import JOBS, attempts, candidate, env, expire_lease, new_job, photo, worker
from tests.test_diary import create, sample
from tests.test_identity import API, bearer, signed_in
from tests.support import migrate


def test_untrusted_qwen_host_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=token_urlsafe(48),
                 ai_base_url="https://unexpected.example.test/compatible-mode/v1")


def test_partial_photo_set_never_reaches_provider(env):
    app, client = env
    auth = bearer(signed_in(client))
    first, second = photo(client, auth), photo(client, auth)
    queued = new_job(client, auth, [first, second]).json()
    with app.state.session_factory.begin() as db:
        db.execute(delete(AiJobMedia).where(AiJobMedia.job_id == queued["id"], AiJobMedia.media_id == second))

    class MustNotSend:
        async def analyze(self, images):
            pytest.fail("Incomplete photo set reached provider")

    assert asyncio.run(worker(app, MustNotSend()).process_once())
    assert attempts(app, queued["id"])[0].status == "not_sent"


def test_global_attempt_history_survives_owner_deletion(env):
    app, client = env
    app.state.settings.ai_global_daily_limit = 1
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)]).json()["id"]
    assert asyncio.run(worker(app).process_once())
    assert attempts(app, identifier)[0].status == "succeeded"
    with app.state.session_factory.begin() as db:
        db.execute(delete(User).where(User.username == "reader"))
    other = bearer(signed_in(client, "other"))
    assert not client.get(API + "/ai/usage", headers=other).json()["available"]


def test_recover_lost_create_response_is_owner_scoped(env):
    _, client = env
    auth = bearer(signed_in(client))
    other = bearer(signed_in(client, "other"))
    key = uuid4().hex
    image = photo(client, auth)
    queued = new_job(client, auth, [image], key=key).json()
    path = JOBS + "/recover"
    result = client.get(path, headers=auth, params={"request_key": key})
    assert result.status_code == 200
    assert result.json()["id"] == queued["id"] and result.json()["media_ids"] == [image]
    assert client.get(path, headers=other, params={"request_key": key}).json() is None


@pytest.mark.parametrize("url", [
    "http://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1",
    "https://other.example@dashscope.aliyuncs.com/compatible-mode/v1",
    "https://dashscope.aliyuncs.com:444/compatible-mode/v1",
    "https://dashscope.aliyuncs.com/proxy/compatible-mode/v1",
    "https://trial.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1?a=b",
    "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1\n",
])
def test_qwen_endpoint_rejects_variants_outside_the_allowlist(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=token_urlsafe(48), ai_base_url=url)


@pytest.mark.parametrize("host", ["dashscope-intl.aliyuncs.com", "llm-fixture.cn-beijing.maas.aliyuncs.com",
                                  "workspace-1.eu-central-1.maas.aliyuncs.com"])
def test_qwen_endpoint_allows_documented_regional_variants(host):
    base = f"https://{host}/compatible-mode/v1"
    assert Settings(_env_file=None, jwt_secret=token_urlsafe(48), ai_base_url=base + "/").ai_base_url == base


def qwen_settings(app, limit):
    settings = app.state.settings
    settings.ai_provider = "qwen"
    settings.ai_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    settings.ai_api_key = SecretStr(token_urlsafe(44))
    settings.ai_model = "qwen3-vl-flash"
    settings.ai_qwen_cumulative_limit = limit
    return settings


def spent(app):
    with app.state.session_factory() as db:
        return db.get(AiCallBudget, "qwen").spent


def test_qwen_cumulative_counts_automatic_retry_and_survives_midnight_restart_and_purge(env):
    app, client = env
    qwen_settings(app, 2)
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    path = JOBS + "/" + new_job(client, auth, [image]).json()["id"]

    class RateLimited:
        async def analyze(self, images):
            raise ProviderError("ai_rate_limited", retryable=True)

    assert asyncio.run(worker(app, RateLimited()).process_once()) and spent(app) == 1
    yesterday = utcnow() - timedelta(days=1)
    with app.state.session_factory.begin() as db:
        db.execute(update(AiUsageLog).values(created_at=yesterday))
        db.execute(update(AiJob).values(available_at=utcnow()))
    assert client.get(API + "/ai/usage", headers=auth).json()["used"] == 0
    assert asyncio.run(worker(app, RateLimited()).process_once()) and spent(app) == 2
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).values(available_at=utcnow()))
    assert worker(app).claim() is None
    assert client.get(path, headers=auth).json()["error_code"] == "ai_cumulative_limit"
    with app.state.session_factory.begin() as db:
        db.execute(update(AiUsageLog).values(created_at=utcnow() - timedelta(days=40)))
    assert worker(app).purge()[1] == 0
    assert len(attempts(app, path.rsplit("/", 1)[-1])) == 2
    assert spent(app) == 2
    assert new_job(client, auth, [image]).json()["error"]["code"] == "ai_cumulative_limit"


def test_before_send_refund_and_dispatch_lease_unknown_keep_budget_conservative(env):
    app, client = env
    qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    identifier = new_job(client, auth, [image]).json()["id"]
    service = worker(app)
    unsent = service.claim()
    expire_lease(app, unsent)
    next_claim = worker(app).claim()
    assert next_claim.token != unsent.token and spent(app) == 0
    assert service.dispatch(next_claim) and spent(app) == 1
    service.finish(next_claim, ProviderError("ai_before_send", sent=False, retryable=True))
    assert spent(app) == 0
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).values(available_at=utcnow()))
    dispatched = worker(app).claim()
    assert service.dispatch(dispatched)
    expire_lease(app, dispatched)
    assert worker(app).claim() is None
    service.finish(dispatched, ProviderError("ai_before_send", sent=False))
    assert spent(app) == 1
    assert client.get(JOBS + "/" + identifier, headers=auth).json()["error_code"] == "ai_result_unknown"


def test_two_prepared_workers_can_consume_only_one_final_cumulative_slot(env):
    app, client = env
    settings = qwen_settings(app, 1)
    settings.ai_max_concurrent_jobs = 2
    for name in ("budget_a", "budget_b"):
        headers = bearer(signed_in(client, name))
        assert new_job(client, headers, [photo(client, headers)]).status_code == 202
    services = [worker(app), worker(app)]
    claims = [service.claim() for service in services]
    assert claims[0].job_id != claims[1].job_id
    prepared = [service.photos(claim) for service, claim in zip(services, claims)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda index: services[index].dispatch(claims[index], prepared[index]), range(2)))
    assert results.count(True) == 1 and spent(app) == 1


def test_cancel_after_dispatch_then_settle_does_not_return_a_paid_slot(env):
    app, client = env
    qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)]).json()["id"]
    service = worker(app)
    claim = service.claim()
    assert service.dispatch(claim)
    assert client.post(JOBS + "/" + identifier + "/cancel", headers=auth).json()["status"] == "cancelled"
    service.finish(claim, ProviderError("ai_result_unknown"))
    assert attempts(app, identifier)[0].status == "unknown" and spent(app) == 1
    assert client.get(JOBS + "/" + identifier, headers=auth).json()["result"] is None


@pytest.mark.parametrize("change", ["corrupt", "missing", "after_prepare", "reorder"])
def test_incomplete_or_changed_bytes_fail_before_dispatch(env, change):
    app, client = env
    qwen_settings(app, 3)
    auth = bearer(signed_in(client))
    ids = [photo(client, auth), photo(client, auth)]
    job = new_job(client, auth, ids).json()
    service = worker(app)
    claim = service.claim()
    with app.state.session_factory() as db:
        path = service.storage.path(db.get(MediaAsset, ids[0]).original_key)
    if change == "after_prepare":
        prepared = service.photos(claim)
        path.unlink()
        assert not service.dispatch(claim, prepared)
    else:
        if change == "missing":
            path.unlink()
        elif change == "corrupt":
            path.write_bytes(b"x" * path.stat().st_size)
        else:
            with app.state.session_factory.begin() as db:
                db.execute(update(AiJobMedia).where(AiJobMedia.media_id == ids[0]).values(sort_order=3))
        with pytest.raises(ProviderError) as error:
            service.photos(claim)
        assert not error.value.sent
        service.finish(claim, error.value)
    assert spent(app) == 0 and attempts(app, job["id"])[0].status == "not_sent"


def test_heartbeat_stales_and_comes_back_without_affecting_manual_meals(env):
    app, client = env
    auth = bearer(signed_in(client))
    path = API + "/ai/capabilities"
    assert not client.get(path, headers=auth).json()["worker_online"]
    assert create(client, auth).status_code == 201
    worker(app).heartbeat()
    assert client.get(path, headers=auth).json()["worker_online"]
    with app.state.session_factory.begin() as db:
        db.execute(update(AiWorkerHeartbeat).values(checked_at=utcnow() - timedelta(seconds=13)))
    assert not client.get(path, headers=auth).json()["worker_online"]
    assert create(client, auth).status_code == 201
    worker(app).heartbeat()
    assert client.get(path, headers=auth).json()["worker_online"]


def test_ai_source_requires_original_media_and_summary_distinguishes_unknown_zero_and_edited(env):
    app, client = env
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    job_id = new_job(client, auth, [image]).json()["id"]
    assert asyncio.run(worker(app).process_once())
    job = client.get(JOBS + "/" + job_id, headers=auth).json()
    edited = candidate(job, 1, category="自定义", calories_kcal=0, protein_g=None)
    foods = [candidate(job), edited, {"food_name": "白水", "calories_kcal": 0}]
    assert create(client, auth, sample(items=foods)).json()["error"]["code"] == "ai_candidate_context"
    saved = create(client, auth, sample(media_ids=[image], items=foods))
    assert saved.status_code == 201
    assert [item["source"] for item in saved.json()["items"]] == ["ai", "ai_edited", "manual"]
    summary = client.get(API + "/statistics/daily?date=2026-12-31", headers=auth).json()
    assert summary["nutrition"]["calories_kcal"] == {"value": 230.0, "known_items": 3, "complete": True}
    assert summary["nutrition_sources"]["calories_kcal"] == {"estimated": 1, "edited": 1, "simulated": 2}
    assert summary["nutrition"]["protein_g"]["known_items"] == 1
    assert summary["nutrition_sources"]["protein_g"]["edited"] == 0


def test_phase_4_upgrade_backfills_count_without_losing_jobs_links_or_history(settings):
    from tests.support import legacy_account, legacy_photo

    migrate(settings, "0003_ai_recognition")
    with TestClient(create_app(settings)) as before:
        with before.app.state.session_factory.begin() as db:
            owner, headers, _ = legacy_account(db, settings)
            media, _ = legacy_photo(db, settings, owner)
        identifier, key = str(uuid4()), uuid4().hex
        result = {"schema_version": "1", "status": "no_food", "foods": [], "warnings": []}
        fingerprint = sha256(json.dumps({"media_ids": [media], "consent_version": CONSENT_VERSION},
                                        separators=(",", ":")).encode()).hexdigest()
        with before.app.state.session_factory.begin() as db:
            metadata = MetaData()
            metadata.reflect(db.connection(), only=("ai_jobs", "ai_job_media", "ai_usage_logs"))
            now = utcnow().replace(tzinfo=None)
            db.execute(metadata.tables["ai_jobs"].insert().values(
                id=identifier, user_id=owner, request_key=key, fingerprint=fingerprint, job_type="food_recognition",
                status="succeeded", provider="qwen", model="qwen3-vl-flash", prompt_version=PROMPT_VERSION,
                consent_version=CONSENT_VERSION, attempt_count=3, max_attempts=3, result_json=result,
                available_at=now, expires_at=now + timedelta(minutes=15), completed_at=now, created_at=now, updated_at=now,
            ))
            db.execute(metadata.tables["ai_job_media"].insert().values(
                user_id=owner, job_id=identifier, media_id=media, sort_order=0,
            ))
            db.execute(metadata.tables["ai_usage_logs"].insert(), [
                dict(id=str(uuid4()), user_id=owner, job_id=identifier, provider=provider, model="fixture",
                     status=status, usage_known=False, hold_until=now, created_at=now)
                for provider, status in (("qwen", "succeeded"), ("qwen", "unknown"), ("qwen", "dispatching"),
                                         ("qwen", "reserved"), ("qwen", "not_sent"), ("fake", "succeeded"))
            ])
    migrate(settings)
    with TestClient(create_app(settings)) as after:
        assert after.get(API + "/ready").status_code == 200
        job = after.get(JOBS + "/" + identifier, headers=headers).json()
        assert job["result"] == result and job["media_ids"] == [media]
        assert new_job(after, headers, [media], key=key).json()["id"] == identifier
        assert len(attempts(after.app, identifier)) == 6 and spent(after.app) == 3
        assert after.get(API + "/media/" + media, headers=headers).status_code == 200


def test_benchmark_fixture_validation_and_csv_comparison():
    cases, images = dataset()
    assert (len(cases), images) == (11, 12)
    same_plate = next(case for case in cases if case["case"] == "same-plate")
    evidence = compare(same_plate, "recognized", ["番茄炒蛋", "西红柿炒鸡蛋", "米饭"])
    assert evidence == {"missing": "", "wrong": "米饭", "duplicate": "番茄炒蛋"}
    assert compare(same_plate, "unrecognized", [])["missing"] == "番茄炒蛋"
    assert spreadsheet_row({"name": "=SUM(1)", "amount": 2}) == {"name": "'=SUM(1)", "amount": 2}


def test_recovery_edit_context_and_expired_candidates_keep_manual_save_available(env):
    app, client = env
    auth = bearer(signed_in(client))
    first = create(client, auth).json()
    second = create(client, auth).json()
    image = photo(client, auth)
    task = new_job(client, auth, [image], form_meal_id=first["id"]).json()
    assert asyncio.run(worker(app).process_once())
    path = JOBS + "/recover"
    assert client.get(path, headers=auth, params={"form_meal_id": second["id"]}).json() is None
    result = client.get(path, headers=auth, params={"form_meal_id": first["id"]}).json()
    assert result["id"] == task["id"] and result["media_ids"] == [image]
    values = candidate(result)
    denied = client.patch(API + "/meals/" + second["id"], headers=auth,
                          json=sample(version=1, media_ids=[image], items=[values]))
    assert denied.json()["error"]["code"] == "ai_candidate_context"
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).where(AiJob.id == result["id"]).values(completed_at=utcnow() - timedelta(days=8)))
    expired = client.patch(API + "/meals/" + first["id"], headers=auth,
                           json=sample(version=1, media_ids=[image], items=[values]))
    assert expired.json()["error"]["code"] == "ai_candidate_unavailable"
    del values["ai_reference"]
    saved = client.patch(API + "/meals/" + first["id"], headers=auth,
                         json=sample(version=1, media_ids=[image], items=[values]))
    assert saved.status_code == 200 and saved.json()["items"][0]["source"] == "manual"
