import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.database import utcnow
from app.main import create_app
from app.models.ai import AiJob, AiJobMedia, AiUsageLog
from app.models.diary import MediaAsset
from app.services import storage
from app.services.ai_prompt import CONSENT_VERSION
from app.services.ai_provider import FakeVisionProvider, ProviderError
from app.services.ai_worker import AiWorker
from tests.support import isolated_settings, migrate
from tests.test_diary import create as save_meal
from tests.test_diary import sample, upload
from tests.test_identity import API, BROWSER, bearer, signed_in

JOBS = API + "/ai/jobs"


@pytest.fixture
def env(tmp_path):
    settings = isolated_settings(tmp_path / "jobs-test.db", ai_enabled=True, ai_provider="fake")
    migrate(settings)
    app = create_app(settings)
    with TestClient(app) as client:
        yield app, client


def new_job(client, headers, ids, key=None, **changes):
    return client.post(JOBS, headers={**headers, "Idempotency-Key": key or uuid4().hex},
                       json={"media_ids": ids, "consent_version": CONSENT_VERSION} | changes)


def photo(client, headers):
    result = upload(client, headers)
    assert result.status_code == 201
    return result.json()["id"]


def create_for(env, username="reader"):
    _, client = env
    headers = bearer(signed_in(client, username))
    identifier = photo(client, headers)
    response = new_job(client, headers, [identifier])
    assert response.status_code == 202
    return headers, identifier, response.json()["id"]


def worker(app, provider=None):
    return AiWorker(app.state.settings, app.state.session_factory, provider or FakeVisionProvider())


def attempts(app, identifier):
    with app.state.session_factory() as db:
        return db.scalars(select(AiUsageLog).where(AiUsageLog.job_id == identifier)
                          .order_by(AiUsageLog.created_at)).all()


def expire_lease(app, claim):
    past = utcnow() - timedelta(seconds=1)
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).where(AiJob.id == claim.job_id).values(lease_until=past))
        db.execute(update(AiUsageLog).where(AiUsageLog.id == claim.token).values(hold_until=past))


def test_creation_and_retry_keys_and_consent_are_bound_to_payload(env):
    app, client = env
    headers = bearer(signed_in(client))
    a, b = photo(client, headers), photo(client, headers)
    key = uuid4().hex
    assert new_job(client, headers, [a], consent_version="stale").json()["error"]["code"] == "ai_consent_required"
    first = new_job(client, headers, [a, b], key=key)
    assert first.status_code == 202 and first.json()["simulated"]
    assert new_job(client, headers, [a, b], key=key).json() == first.json()
    assert new_job(client, headers, [b, a], key=key).json()["error"]["code"] == "idempotency_conflict"
    assert new_job(client, headers, [a]).json()["error"]["code"] == "ai_job_active"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AiJob)) == 1
        assert db.scalars(select(AiJobMedia.media_id).order_by(AiJobMedia.sort_order)).all() == [a, b]


def test_missing_key_keeps_manual_diary_available(client):
    settings = client.app.state.settings
    settings.ai_enabled = True
    settings.ai_model = "qwen3-vl-flash"
    settings.ai_base_url = "https://provider.example.test/compatible-mode/v1"
    headers = bearer(signed_in(client))
    assert not client.get(API + "/ai/capabilities", headers=headers).json()["available"]
    assert new_job(client, headers, [str(uuid4())]).json()["error"]["code"] == "ai_unavailable"
    assert save_meal(client, headers).status_code == 201


def test_auth_ownership_and_provider_configuration_cannot_be_passed_by_user(env):
    app, client = env
    b, b_photo, identifier = create_for(env, "owner_b")
    a = bearer(signed_in(client, "owner_a"))
    private = JOBS + "/" + identifier
    assert client.get(API + "/ai/capabilities").status_code == 401
    assert client.get(API + "/ai/usage").status_code == 401
    assert new_job(client, {}, [b_photo]).status_code == 401
    assert new_job(client, a, [b_photo]).status_code == 404
    assert new_job(client, b, [b_photo], base_url="https://unexpected.example.test").status_code == 422
    assert client.get(private, headers=a).json() == client.get(JOBS + "/" + str(uuid4()), headers=a).json()
    for suffix in ("/cancel", "/retry"):
        rejected = client.post(private + suffix, headers={**a, "Idempotency-Key": uuid4().hex},
                               json={"consent_version": CONSENT_VERSION})
        assert rejected.status_code == 404
    assert client.post(API + "/auth/logout", headers={**BROWSER, **a}).status_code == 204
    assert new_job(client, a, [b_photo]).status_code == 401
    assert not attempts(app, identifier)


def test_multiple_workers_and_global_quota_are_serialized(env):
    app, client = env
    app.state.settings.ai_max_concurrent_jobs = 4
    app.state.settings.ai_global_daily_limit = 1
    a, _, first = create_for(env, "owner_a")
    b, _, second = create_for(env, "owner_b")
    barrier = Event()

    def compete():
        assert barrier.wait(5)
        return worker(app).claim()

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(compete) for _ in range(6)]
        barrier.set()
        winners = [claim for future in futures if (claim := future.result(10))]
    assert len(winners) == 1 and winners[0].job_id == first
    assert len(attempts(app, first)) == 1 and not attempts(app, second)
    assert client.get(JOBS + "/" + second, headers=b).json()["error_code"] == "ai_quota"
    counts = client.get(API + "/ai/usage", headers=a).json()
    assert counts["used"] == 1 and not counts["available"]


def test_cancel_during_model_call_keeps_slot_and_does_not_publish(env):
    app, client = env
    auth, identifier, job_id = create_for(env)
    entered, proceed = Event(), Event()

    class Paused(FakeVisionProvider):
        async def analyze(self, images):
            entered.set()
            assert await asyncio.to_thread(proceed.wait, 8)
            return await super().analyze(images)

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(asyncio.run, worker(app, Paused()).process_once())
        try:
            assert entered.wait(6)
            assert client.delete(API + "/media/" + identifier, headers=auth).json()["error"]["code"] == "media_in_ai_use"
            # A write through the ordinary API must succeed while the upstream call remains paused.
            assert save_meal(client, auth).status_code == 201
            assert client.post(JOBS + "/" + job_id + "/cancel", headers=auth).json()["status"] == "cancelled"
            assert new_job(client, auth, [identifier]).status_code == 202
            assert worker(app).claim() is None
        finally:
            proceed.set()
        assert running.result(8)
    view = client.get(JOBS + "/" + job_id, headers=auth).json()
    assert view["status"] == "cancelled" and view["result"] is None
    assert attempts(app, job_id)[0].status == "succeeded"


def test_recovery_of_unsent_lease_and_stale_worker_cannot_overwrite(env):
    app, client = env
    headers, _, identifier = create_for(env)
    old = worker(app).claim()
    expire_lease(app, old)
    service = worker(app)
    new = service.claim()
    assert new.token != old.token and service.dispatch(new)
    service.finish(old, ProviderError("ai_result_unknown"))
    outcome = asyncio.run(service.provider.analyze(service.photos(new)))
    service.finish(new, outcome)
    job = client.get(JOBS + "/" + identifier, headers=headers).json()
    assert job["status"] == "succeeded" and job["attempt_count"] == 2
    assert [entry.status for entry in attempts(app, identifier)] == ["not_sent", "succeeded"]


def test_recovery_after_dispatch_requires_explicit_retry_and_counts_unknown(env):
    app, client = env
    headers, _, identifier = create_for(env)
    service = worker(app)
    claim = service.claim()
    assert service.dispatch(claim)
    expire_lease(app, claim)
    assert worker(app).claim() is None
    path = JOBS + "/" + identifier
    assert client.get(path, headers=headers).json()["error_code"] == "ai_result_unknown"
    idem = {**headers, "Idempotency-Key": uuid4().hex}
    payload = {"consent_version": CONSENT_VERSION}
    assert client.post(path + "/retry", headers=idem, json=payload).json()["error"]["code"] == "ai_retry_confirmation"
    accepted = client.post(path + "/retry", headers=idem, json=payload | {"accept_unknown_charge": True})
    assert accepted.status_code == 202
    assert client.post(path + "/retry", headers=idem, json=payload).json()["error"]["code"] == "idempotency_conflict"
    assert asyncio.run(worker(app).process_once())
    assert client.post(path + "/retry", headers=idem, json=payload | {"accept_unknown_charge": True}).json()["status"] == "succeeded"
    assert [row.status for row in attempts(app, identifier)] == ["unknown", "succeeded"]
    assert client.get(API + "/ai/usage", headers=headers).json()["used"] == 2


@pytest.mark.parametrize(("code", "sent", "recorded", "used"), [
    ("ai_before_send", False, "not_sent", 0), ("ai_rate_limited", True, "failed", 1),
    ("ai_invalid_result", True, "failed", 1), ("ai_result_unknown", True, "unknown", 1),
])
def test_failures_and_automatic_retry_accounting(env, code, sent, recorded, used):
    app, client = env
    auth, _, identifier = create_for(env)
    retryable = code in ("ai_before_send", "ai_rate_limited")

    class Failing:
        async def analyze(self, images):
            raise ProviderError(code, sent=sent, retryable=retryable)

    assert asyncio.run(worker(app, Failing()).process_once())
    result = client.get(JOBS + "/" + identifier, headers=auth).json()
    assert result["status"] == ("pending" if retryable else "failed")
    assert result["error_code"] == code and result["result"] is None
    assert [(item.status, item.usage_known) for item in attempts(app, identifier)] == [(recorded, False)]
    assert client.get(API + "/ai/usage", headers=auth).json()["used"] == used
    if retryable:
        with app.state.session_factory.begin() as db:
            db.execute(update(AiJob).where(AiJob.id == identifier).values(available_at=utcnow()))
        assert asyncio.run(worker(app).process_once())
        assert client.get(API + "/ai/usage", headers=auth).json()["used"] == used + 1


def test_expired_jobs_release_media_and_purge_keeps_usage_tombstone(env):
    app, client = env
    auth, image, identifier = create_for(env)
    assert asyncio.run(worker(app).process_once())
    past = utcnow() - timedelta(days=9)
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).where(AiJob.id == identifier).values(completed_at=past))
        db.execute(update(MediaAsset).where(MediaAsset.id == image).values(updated_at=past))
    assert client.get(JOBS + "/" + identifier, headers=auth).status_code == 404
    assert worker(app).purge() == (1, 0)
    with app.state.session_factory() as db:
        assert db.scalar(select(AiUsageLog)).job_id is None
        assert app.state.storage.sweep(db, apply=True)["unreferenced_assets"] == 1
    assert client.get(API + "/media/" + image, headers=auth).status_code == 404


def test_sweep_rechecks_task_reference_after_concurrent_creation(env, monkeypatch):
    app, client = env
    headers = bearer(signed_in(client))
    identifier = photo(client, headers)
    with app.state.session_factory.begin() as db:
        db.execute(update(MediaAsset).where(MediaAsset.id == identifier).values(updated_at=utcnow() - timedelta(days=3)))
    identified, resume = Event(), Event()
    owner_lock = storage.lock_owner

    def paused(db, owner):
        identified.set()
        assert resume.wait(5)
        owner_lock(db, owner)

    def sweep():
        with app.state.session_factory() as db:
            return app.state.storage.sweep(db, apply=True)

    monkeypatch.setattr(storage, "lock_owner", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        cleanup = pool.submit(sweep)
        try:
            assert identified.wait(5)
            job = new_job(client, headers, [identifier])
            assert job.status_code == 202
        finally:
            resume.set()
        assert cleanup.result(7)["unreferenced_assets"] == 0
    assert client.get(API + "/media/" + identifier, headers=headers).status_code == 200
    assert asyncio.run(worker(app).process_once())
    assert sweep()["unreferenced_assets"] == 1


def candidate(job, index=0, **changes):
    food = job["result"]["foods"][index].copy()
    identifier = food.pop("id")
    food.pop("uncertainty")
    return food | {"ai_reference": {"job_id": job["id"], "candidate_id": identifier}} | changes


def test_ai_only_writes_after_confirmation_and_sources_and_ids_survive_edit(env):
    app, client = env
    auth, image, identifier = create_for(env)
    assert asyncio.run(worker(app).process_once())
    assert client.get(API + "/meals", headers=auth).json()["total"] == 0
    job = client.get(JOBS + "/" + identifier, headers=auth).json()
    payload = sample(media_ids=[image], items=[candidate(job), candidate(job, 1, food_name="杂粮饭")])
    key = uuid4().hex
    saved = save_meal(client, auth, payload, key)
    assert saved.status_code == 201
    meal = saved.json()
    assert [item["source"] for item in meal["items"]] == ["ai", "ai_edited"]
    assert all(item["ai_job_id"] == identifier and item["ai_provider"] == "fake" for item in meal["items"])
    assert save_meal(client, auth, payload, key).status_code == 200
    assert save_meal(client, auth, payload).json()["error"]["code"] == "ai_candidate_used"
    path = API + "/meals/" + meal["id"]
    first, second = meal["items"]
    proposed = [{key: item[key] for key in ("id", "food_name", "category", "weight_g", "calories_kcal", "protein_g",
                                           "carbohydrates_g", "fat_g", "note")} for item in (second, first)]
    proposed[0]["note"] = "只改备注"
    with app.state.session_factory.begin() as db:
        db.execute(update(AiJob).values(completed_at=utcnow() - timedelta(days=9)))
    assert worker(app).purge()[0] == 1
    changed = client.patch(path, headers=auth, json=sample(note="新备注", version=1, media_ids=[image], items=proposed))
    assert changed.status_code == 200
    assert [(item["id"], item["source"]) for item in changed.json()["items"]] == [(second["id"], "ai_edited"), (first["id"], "ai")]


def test_forged_candidate_and_item_references_are_rejected(env):
    app, client = env
    auth, _, identifier = create_for(env)
    assert asyncio.run(worker(app).process_once())
    job = client.get(JOBS + "/" + identifier, headers=auth).json()
    a = save_meal(client, auth, sample(items=[{"food_name": "汤"}])).json()
    other = bearer(signed_in(client, "other"))
    b = save_meal(client, other).json()
    assert save_meal(client, other, sample(items=[candidate(job)])).status_code == 404
    spoof = candidate(job)
    spoof["ai_reference"]["candidate_id"] = str(uuid4())
    assert save_meal(client, auth, sample(items=[spoof])).status_code == 404
    assert save_meal(client, auth, sample(items=[candidate(job), candidate(job)])).status_code == 422
    assert save_meal(client, auth, sample(items=[{"food_name": "水", "source": "ai"}])).status_code == 422
    same_owner = save_meal(client, auth).json()
    path = API + "/meals/" + a["id"]
    for foreign in (b, same_owner):
        changed = client.patch(path, headers=auth, json=sample(version=1, items=[
            {"food_name": "水", "id": foreign["items"][0]["id"]},
        ]))
        assert changed.json()["error"]["code"] == "meal_item_not_found"
    assert client.get(path, headers=auth).json()["version"] == 1
