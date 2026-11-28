from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.database import utcnow
from app.models.diary import MediaAsset
from app.models.stickers import MediaDerivative, StickerJob
from app.services.sticker_image import StickerImageError
from app.services.sticker_worker import StickerWorker
from app.services.storage import storage_usage
from tests.test_diary import create, sample, upload
from tests.test_identity import API, bearer, signed_in

JOBS = API + "/stickers/jobs"
CATALOG = API + "/catalog"


@pytest.fixture
def lab(app, client):
    app.state.settings.sticker_enabled = True
    app.state.settings.sticker_provider = "fake"
    worker = StickerWorker(app.state.settings, app.state.session_factory)
    worker.heartbeat()
    return client, bearer(signed_in(client, "sticker_reader")), worker


def put(client, auth):
    fixture = Path(__file__).resolve().parents[2] / "docs/ai-benchmark/images/homestyle-lunch.jpg"
    response = upload(client, auth, contents=fixture.read_bytes())
    assert response.status_code == 201
    return response.json()["id"]


def queue(client, auth, photo):
    response = client.post(JOBS, headers=auth, json={"media_id": photo})
    assert response.status_code == 202, response.json()
    return response.json()["id"]


def job(client, auth, identifier):
    return client.get(JOBS + "/" + identifier, headers=auth).json()


def test_sticker_deduplication_transparency_outline_storage_and_isolation(lab):
    client, owner, worker = lab
    other = bearer(signed_in(client, "sticker_other"))
    photo = put(client, owner)
    identifier = queue(client, owner, photo)
    assert queue(client, owner, photo) == identifier
    assert job(client, owner, identifier)["timings"] is None
    assert client.delete(API + "/media/" + photo, headers=owner).status_code == 409
    assert client.post(JOBS, headers=other, json={"media_id": photo}).status_code == 404
    assert client.get(JOBS + "/" + identifier, headers=other).status_code == 404
    assert client.post(JOBS + "/" + identifier + "/cancel", headers=other).status_code == 404
    assert worker.run_once()
    completed = job(client, owner, identifier)
    assert completed["status"] == "succeeded"
    timings = completed["timings"]
    assert set(timings) == {"queue_ms", "image_ms", "inference_ms", "encode_ms", "processing_ms", "ready_age_ms"}
    assert all(isinstance(value, int) and value >= 0 for value in timings.values())
    assert timings["processing_ms"] >= sum(timings[field] for field in ("image_ms", "inference_ms", "encode_ms"))
    assert queue(client, owner, photo) == identifier
    assert not worker.run_once()
    image_path = API + "/media/" + photo + "/sticker"
    for suffix in ("", "/cutout", "/thumbnail"):
        assert client.get(image_path + suffix, headers=other).status_code == 404
    assert client.delete(API + "/media/" + photo, headers=other).status_code == 404
    raw = client.get(image_path + "/cutout", headers=owner)
    sticker = client.get(image_path, headers=owner)
    thumb = client.get(image_path + "/thumbnail", headers=owner)
    assert raw.status_code == sticker.status_code == thumb.status_code == 200
    assert sticker.headers["Cache-Control"] == "no-store"
    with Image.open(BytesIO(raw.content)) as cutout, Image.open(BytesIO(sticker.content)) as outlined:
        assert cutout.mode == outlined.mode == "RGBA"
        assert outlined.width > cutout.width and outlined.height > cutout.height
        assert outlined.getpixel((0, 0))[3] == 0
        assert any(red >= 250 and green >= 250 and blue >= 248 and alpha > 100
                   for red, green, blue, alpha in outlined.get_flattened_data())
    with worker.sessions() as db:
        row = db.scalar(select(MediaDerivative))
        assert row.source_media_id == photo
        assert row.size_bytes == sum(len(result.content) for result in (raw, sticker, thumb))
        assert storage_usage(db, row.user_id)[0] == 4
        files = [worker.storage.path(key) for key in (row.storage_key, row.cutout_key, row.thumbnail_key)]
    assert client.delete(API + "/media/" + photo, headers=owner).status_code == 204
    assert not any(path.exists() for path in files)
    assert client.get(image_path, headers=owner).status_code == 404


def test_two_workers_restart_cancel_and_old_claim_cannot_replace_result(lab):
    client, owner, worker = lab
    photo = put(client, owner)
    identifier = queue(client, owner, photo)
    backup = StickerWorker(worker.settings, worker.sessions)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda service: service.claim(), [worker, backup]))
    assert sum(claim is not None for claim in claims) == 1
    prior = next(claim for claim in claims if claim)
    with worker.sessions.begin() as db:
        db.get(StickerJob, identifier).lease_until = utcnow() - timedelta(seconds=1)
    recovered = backup.claim()
    assert recovered.id == prior.id and recovered.token != prior.token
    assert job(client, owner, identifier)["attempts"] == 2
    assert client.post(JOBS + "/" + identifier + "/cancel", headers=owner).json()["status"] == "cancelled"
    worker.finish(prior, error="inference_failed")
    assert client.post(JOBS + "/" + identifier + "/retry", headers=owner, json={}).status_code == 409
    backup.finish(recovered, error="inference_failed")
    resized = {"crop": {"left": .12, "top": .08, "width": .8, "height": .77}}
    assert client.post(JOBS + "/" + identifier + "/retry", headers=owner, json=resized).status_code == 202
    assert backup.run_once()
    assert job(client, owner, identifier)["ready"] and job(client, owner, identifier)["manual"]
    worker.finish(prior, error="inference_failed")
    assert job(client, owner, identifier)["status"] == "succeeded"


@pytest.mark.parametrize("failure", ["model_unavailable", "inference_timeout", "inference_failed"])
def test_processing_failure_leaves_original_and_manual_meal_available(lab, failure):
    client, owner, worker = lab
    photo = put(client, owner)
    identifier = queue(client, owner, photo)

    def broken(*_):
        raise StickerImageError(failure)

    worker.processor = broken
    assert worker.run_once()
    assert job(client, owner, identifier)["error_code"] == failure
    assert queue(client, owner, photo) == identifier and not worker.run_once()
    assert create(client, owner, sample(media_ids=[photo])).status_code == 201
    assert client.get(API + "/media/" + photo, headers=owner).status_code == 200


def test_processing_does_not_hold_db_write_lock_inference_independent_of_ai(lab):
    client, owner, worker = lab
    assert worker.settings.ai_enabled is False
    photo = put(client, owner)
    identifier = queue(client, owner, photo)
    entered, release = Event(), Event()
    normal = worker.processor

    def wait_for_save(raw, crop, tick):
        entered.set()
        assert release.wait(12)
        return normal(raw, crop, tick)

    worker.processor = wait_for_save
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(worker.run_once)
        try:
            assert entered.wait(5)
            meal = create(client, owner, sample(media_ids=[photo])).json()
            assert client.get(CATALOG, headers=owner).json()["collected"] == 2
            assert job(client, owner, identifier)["status"] == "running"
        finally:
            release.set()
        assert task.result()
    assert job(client, owner, identifier)["ready"]
    assert client.delete(API + "/media/" + photo, headers=owner).status_code == 409
    calendar = client.get(API + "/calendar?month=2026-12", headers=owner).json()
    assert calendar["days"][0]["representative_media_id"] == photo
    assert client.delete(API + "/meals/" + meal["id"], headers=owner).status_code == 204


def test_storage_quotas_and_disk_guard_are_safe_failures(lab):
    client, owner, worker = lab
    photo = put(client, owner)
    identifier = queue(client, owner, photo)
    worker.settings.media_user_files = 3
    assert worker.run_once()
    assert job(client, owner, identifier)["error_code"] == "media_quota"
    retried = client.post(JOBS + "/" + identifier + "/retry", headers=owner, json={})
    assert retried.status_code == 202 and retried.json()["timings"] is None
    worker.settings.sticker_min_free_bytes = 10**17
    assert worker.run_once()
    assert job(client, owner, identifier)["error_code"] == "disk_low"
    assert not list(worker.storage.root.glob("stickers/*.webp"))


def test_damaged_source_and_offline_worker(lab):
    client, owner, worker = lab
    photo = put(client, owner)
    identifier = queue(client, owner, photo)
    with worker.sessions.begin() as db:
        worker.storage.path(db.get(MediaAsset, photo).original_key).write_bytes(b"wrong hash")
    assert worker.run_once()
    assert job(client, owner, identifier)["error_code"] == "source_invalid"
    worker.settings.sticker_enabled = False
    another = put(client, owner)
    assert client.post(JOBS, headers=owner, json={"media_id": another}).status_code == 503
    assert create(client, owner, sample(media_ids=[another])).status_code == 201


def test_catalog_canonical_occasions_dates_history_edit_merge_delete_and_isolation(lab):
    client, owner, _ = lab
    other = bearer(signed_in(client, "catalog_other"))
    photo = put(client, owner)
    first_data = sample(local_date="2026-11-15", media_ids=[photo],
                        items=[{"food_name": "牛角包", "category": "甜点"}, {"food_name": "可颂（牛角面包）", "category": "甜点"}])
    key = uuid4().hex
    first = create(client, owner, first_data, key).json()
    assert create(client, owner, first_data, key).status_code == 200
    second = create(client, owner, sample(local_date="2026-12-10", items=[{"food_name": "可颂", "category": "甜点"}])).json()
    source_meal = create(client, owner, sample(items=[{"food_name": "咸奶油酥角", "category": "甜点"}])).json()
    listing = client.get(CATALOG + "?category=甜点&search=牛角包", headers=owner).json()
    assert listing["collected"] == 2 and listing["total"] == 1
    item = listing["items"][0]
    assert (item["display_name"], item["occasions"], item["details"]) == ("可颂", 2, 3)
    assert (item["first_eaten"], item["last_eaten"], item["cover_media_id"]) == ("2026-11-15", "2026-12-10", photo)
    assert item["cover_whole_meal"]
    item_path = CATALOG + "/" + item["id"]
    assert client.get(item_path + "/history?limit=1", headers=owner).json()["items"][0]["meal_id"] == second["id"]
    assert client.patch(item_path, headers=owner, json={"display_name": "酥层日记", "category": "面包", "is_favorite": True,
                                                       "cover_media_id": photo}).status_code == 200
    source = client.get(CATALOG + "?search=咸奶油酥角", headers=owner).json()["items"][0]
    request = {"source_id": source["id"], "target_id": item["id"]}
    assert client.post(CATALOG + "/merge", headers=other, json=request).status_code == 404
    assert client.get(item_path + "/history", headers=other).status_code == 404
    assert client.patch(item_path, headers=other, json={"is_favorite": False}).status_code == 404
    merged = client.post(CATALOG + "/merge", headers=owner, json=request).json()
    assert (merged["occasions"], merged["details"], merged["category"], merged["is_favorite"]) == (3, 4, "面包", True)
    assert client.get(API + "/meals/" + source_meal["id"], headers=owner).json()["items"][0]["food_name"] == "咸奶油酥角"
    edit = {**first_data, "version": 1,
            "items": [{"id": first["items"][0]["id"], "food_name": "麦片", "category": "主食"}]}
    result = client.patch(API + "/meals/" + first["id"], headers=owner, json=edit)
    assert result.status_code == 200 and result.json()["items"][0]["id"] == first["items"][0]["id"]
    assert client.get(item_path, headers=owner).json()["occasions"] == 2
    for saved in (second, source_meal):
        assert client.delete(API + "/meals/" + saved["id"], headers=owner).status_code == 204
    assert client.get(CATALOG + "?favorites=true", headers=owner).json()["items"][0]["occasions"] == 0
    assert not client.get(CATALOG + "?category=面包", headers=owner).json()["items"]
