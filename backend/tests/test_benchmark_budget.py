import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, update

from app.core.database import utcnow
from app.models.ai import AiJob, AiUsageLog
from app.services.ai_control import processing_identity
from app.services.ai_prompt import disclosure
from app.services.ai_provider import Analysis, FakeVisionProvider, Usage
from tests import ai_benchmark
from tests.ai_benchmark import run_cases
from tests.benchmark_budget import BudgetPause, LiveBudget, PriceTier
from tests.test_ai_jobs import env, new_job, photo, worker
from tests.test_deepseek import deepseek_settings
from tests.test_identity import bearer, signed_in
from tests.test_phase41 import qwen_settings


def plan(settings, amount=".17", attempts=5):
    if settings.ai_provider == "deepseek":
        return LiveBudget(attempts, Decimal(amount), "USD", "fixture peak rates",
                          (PriceTier.parse("1048576:.3:1.2"),), processing_identity(settings),
                          settings.ai_model, 1024, "deepseek")
    return LiveBudget(attempts, Decimal(amount), "CNY", "fixture rates", tuple(map(PriceTier.parse, (
        "32768:.15:1.5", "131072:.3:3", "262144:.6:6",
    ))), processing_identity(settings), settings.ai_model, 1024)


def open_ledger(app):
    connection = sqlite3.connect(app.state.settings.db_url.database)
    connection.row_factory = sqlite3.Row
    return closing(connection)


def record_call(env, username, input_tokens, output_tokens):
    app, client = env
    auth = bearer(signed_in(client, username))
    consent = disclosure(app.state.settings.ai_provider)[0]
    response = new_job(client, auth, [photo(client, auth)], consent_version=consent)
    assert response.status_code == 202

    class Offline(FakeVisionProvider):
        async def analyze(self, images):
            result = await super().analyze(images)
            return Analysis(result.result, Usage(input_tokens, output_tokens))

    assert asyncio.run(worker(app, Offline()).process_once())
    return response.json()["id"]


def test_browser_and_batch_amount_share_the_ledger_across_script_restarts(env):
    app, _ = env
    settings = qwen_settings(app, 5)
    budget = plan(settings)
    browser_job = record_call(env, "browser_owner", 30_000, 500)
    with app.state.session_factory.begin() as db:
        db.execute(update(AiUsageLog).where(AiUsageLog.job_id == browser_job)
                   .values(created_at=utcnow() - timedelta(days=1)))
    with open_ledger(app) as ledger:
        first = budget.ledger_estimate(ledger)
        assert first.attempts == 1 and first.amount == Decimal(".00525")
        assert budget.next_call_upper_bound == Decimal(".1634304")
        assert budget.safe_launch_limit(first, 5) == 2
    record_call(env, "batch_owner", 60_000, 1000)

    # A new process is represented by a new SQLite connection and pricing object.
    followup = plan(settings)
    with open_ledger(app) as ledger:
        total = followup.ledger_estimate(ledger)
        assert total.attempts == 2 and total.amount == Decimal(".02625") < followup.approved_amount
        with pytest.raises(BudgetPause, match="保守上界"):
            followup.require_next(total, 5)

        class NoNewPaidWork:
            def send(self, method, path):
                assert method == "GET"
                facts = {"available": True, "worker_online": True, "simulated": False, "provider": "qwen"}
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: facts)

            def create_job(self, *_):
                pytest.fail("A new paid case was submitted")

        case = {"case": "next", "focus": "", "photos": [], "status": ["recognized"], "foods": []}
        rows = list(run_cases(NoNewPaidWork(), ledger, [case], SimpleNamespace(run_local="qwen", region="cn-beijing"),
                              followup, cumulative_limit=5))
        assert len(rows) == 1 and "保守上界" in rows[0]["pause_reason"]


@pytest.mark.parametrize(("change", "reason"), [
    ("unknown", "发送状态"), ("missing_tokens", "Token 用量"), ("missing_row", "明细不一致"),
    ("missing_endpoint", "地域端点"), ("out_of_tier", "价格档位"),
])
def test_unsettled_or_unpriceable_history_blocks_the_next_batch(env, change, reason):
    app, _ = env
    settings = qwen_settings(app, 5)
    identifier = record_call(env, "browser_owner", 200, 100)
    with app.state.session_factory.begin() as db:
        rows = AiUsageLog.job_id == identifier
        if change == "unknown":
            db.execute(update(AiUsageLog).where(rows).values(status="unknown"))
        elif change == "missing_tokens":
            db.execute(update(AiUsageLog).where(rows).values(usage_known=False, output_tokens=None))
        elif change == "missing_row":
            db.execute(delete(AiUsageLog).where(rows))
        elif change == "missing_endpoint":
            db.execute(update(AiJob).where(AiJob.id == identifier).values(processing_fingerprint=None))
        else:
            db.execute(update(AiUsageLog).where(rows).values(input_tokens=262_145))
    with open_ledger(app) as ledger, pytest.raises(BudgetPause, match=reason):
        plan(settings).ledger_estimate(ledger)


def test_lifetime_count_remains_a_separate_cap_even_with_money_left(env):
    app, _ = env
    settings = qwen_settings(app, 5)
    record_call(env, "browser_owner", 200, 100)
    with open_ledger(app) as ledger:
        budget = plan(settings, amount="1", attempts=1)
        with pytest.raises(BudgetPause, match="次数"):
            budget.safe_launch_limit(budget.ledger_estimate(ledger), 5)


def test_browser_launch_budget_check_uses_read_only_ledger_without_http(env, monkeypatch, capsys):
    app, _ = env
    settings = qwen_settings(app, 5)
    settings.ai_max_attempts = 1
    settings.ai_max_output_tokens = 1024
    record_call(env, "browser_owner", 30_000, 500)
    monkeypatch.setattr(ai_benchmark, "Settings", lambda: settings)
    monkeypatch.setattr(ai_benchmark.httpx, "Client", lambda **_: pytest.fail("Budget check attempted HTTP"))
    monkeypatch.setattr(sys, "argv", [
        "ai_benchmark", "--check-budget", "--database", settings.db_url.database, "--region", "cn-beijing",
        "--authorized-attempts", "5", "--approved-budget", ".17", "--currency", "CNY",
        "--price-reference", "fixture", "--price-tier", "32768:.15:1.5",
        "--price-tier", "131072:.3:3", "--price-tier", "262144:.6:6",
    ])
    ai_benchmark.main()
    assert json.loads(capsys.readouterr().out) == {
        "spent_attempts": 1, "estimate_total": "0.00525", "next_call_upper_bound": "0.1634304",
        "safe_call_limit": 2, "currency": "CNY",
    }


def test_deepseek_budget_carries_both_batches_without_repricing_qwen(env):
    app, _ = env
    settings = qwen_settings(app, 5)
    record_call(env, "qwen_account", 50_000, 500)
    deepseek_settings(app, 5)
    record_call(env, "deepseek_browser", 30_000, 500)
    with open_ledger(app) as ledger:
        pricing = plan(settings, ".34")
        previous = pricing.ledger_estimate(ledger)
        assert previous.attempts == 1 and previous.amount == Decimal(".0096")
        assert pricing.next_call_upper_bound == Decimal(".3158016")
        assert pricing.safe_launch_limit(previous, 5) == 2
    record_call(env, "deepseek_followup", 60_000, 1000)
    with open_ledger(app) as ledger:
        pricing = plan(settings, ".34")
        total = pricing.ledger_estimate(ledger)
        assert total.attempts == 2 and total.amount == Decimal(".0288")
        with pytest.raises(BudgetPause, match="保守上界"):
            pricing.require_next(total, 5)
