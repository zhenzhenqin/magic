from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.security import COOKIE_NAME
from app.main import create_app
from app.models.diary import Meal, MealItem, MealRequest
from tests.support import migrate
from tests.test_identity import API, BROWSER, bearer, login, signed_in


@pytest.fixture
def owner(client):
    return bearer(signed_in(client))


def sample(**changes):
    return {
        "meal_type": "snack", "local_date": "2026-12-31", "local_time": "23:58", "timezone": "Asia/Shanghai",
        "note": "样例", "items": [{"food_name": "饭团", "calories_kcal": 80.25}, {"food_name": "热茶"}],
        **changes,
    }


def create(client, headers, data=None, key=None):
    return client.post(API + "/meals", json=sample() if data is None else data,
                       headers={**headers, "Idempotency-Key": key or uuid4().hex})


def image_bytes(fmt="JPEG", size=(640, 420), exif=None):
    memory = BytesIO()
    with Image.new("RGB", size, (160, 106, 44)) as image:
        image.save(memory, fmt, **({"exif": exif} if exif else {}))
    return memory.getvalue()


def upload(client, headers, fmt="JPEG", contents=None, filename="fixture.jpg"):
    return client.post(API + "/media/upload", headers=headers,
                       files={"file": (filename, contents if contents is not None else image_bytes(fmt), "image/jpeg")})


def test_migration_preserves_stage_two_identity_and_session(settings):
    migrate(settings, "0001_identity")
    with TestClient(create_app(settings)) as before:
        session = signed_in(before)
        cookie = before.cookies.get(COOKIE_NAME)
        headers = bearer(session)
        assert before.patch(API + "/users/me/settings", headers=headers, json={"timezone": "Asia/Tokyo"}).status_code == 200
    migrate(settings)
    with TestClient(create_app(settings)) as after:
        assert after.get(API + "/users/me", headers=headers).json()["username"] == "reader"
        assert after.get(API + "/users/me/settings", headers=headers).json()["timezone"] == "Asia/Tokyo"
        refreshed = after.post(API + "/auth/refresh", headers={**BROWSER, "Cookie": COOKIE_NAME + "=" + cookie})
        assert refreshed.status_code == 200
        assert create(after, bearer(refreshed)).status_code == 201


def test_meal_crud_summary_and_calendar(client, owner):
    first = create(client, owner)
    assert first.status_code == 201
    meal = first.json()
    assert len(meal["items"]) == 2 and not meal["media"]
    assert meal["items"][1]["weight_g"] is None and meal["items"][1]["calories_kcal"] is None
    assert all(item["source"] == "manual" for item in meal["items"])
    assert meal["version"] == 1
    more = create(client, owner, sample(local_time="12:03"))
    next_month = create(client, owner, sample(local_date="2027-01-01", local_time="00:01", timezone="Asia/Tokyo"))
    assert more.status_code == next_month.status_code == 201
    assert next_month.json()["eaten_at"] == "2026-12-31T15:01:00Z"
    day = client.get(API + "/meals?date=2026-12-31&meal_type=snack", headers=owner).json()
    assert day["total"] == 2
    assert [entry["id"] for entry in day["items"]] == [meal["id"], more.json()["id"]]
    span = client.get(API + "/meals?start=2026-12-31&end=2027-01-01&page=2&limit=1", headers=owner).json()
    assert span["total"] == 3 and span["items"][0]["id"] == meal["id"]
    daily = client.get(API + "/statistics/daily?date=2026-12-31", headers=owner).json()
    assert (daily["meals"], daily["items"]) == (2, 4)
    assert daily["nutrition"]["calories_kcal"] == {"value": 160.5, "complete": False, "known_items": 2}
    assert daily["nutrition"]["protein_g"]["value"] is None
    path = API + "/meals/" + meal["id"]
    edit = client.patch(path, headers=owner, json={**sample(local_date="2027-01-02", meal_type="breakfast"), "version": 1})
    assert edit.status_code == 200 and edit.json()["version"] == 2
    assert client.get(path, headers=owner).json()["local_date"] == "2027-01-02"
    cal = client.get(API + "/calendar?month=2027-01", headers=owner).json()
    assert [entry["date"] for entry in cal["days"]] == ["2027-01-01", "2027-01-02"]
    assert client.delete(path + "?version=2", headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404
    assert client.get(API + "/statistics/daily?date=2027-01-02", headers=owner).json()["nutrition"]["calories_kcal"]["value"] is None


@pytest.mark.parametrize(("timezone", "local", "time", "utc"), [
    ("Asia/Shanghai", "2027-01-01", "00:01", "2026-12-31T16:01:00Z"),
    ("Asia/Tokyo", "2026-03-01", "00:00", "2026-02-28T15:00:00Z"),
    ("America/New_York", "2027-01-01", "23:59", "2027-01-02T04:59:00Z"),
])
def test_timezones_preserve_local_date(client, owner, timezone, local, time, utc):
    saved = create(client, owner, sample(timezone=timezone, local_date=local, local_time=time)).json()
    assert saved["eaten_at"] == utc
    assert client.patch(API + "/users/me/settings", json={"timezone": "UTC"}, headers=owner).status_code == 200
    assert client.get(API + "/meals/" + saved["id"], headers=owner).json()["local_date"] == local


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", 4.567, 100001])
def test_invalid_nutrition(client, owner, value):
    assert create(client, owner, sample(items=[{"food_name": "样例", "calories_kcal": value}])).status_code == 422


def test_nonexistent_local_time(client, owner):
    result = create(client, owner, sample(timezone="America/New_York", local_date="2026-03-08", local_time="02:15"))
    assert result.status_code == 422


def test_idempotency_is_account_scoped_and_has_a_tombstone(client, owner):
    key = "same-browser-save"
    first = create(client, owner, key=key).json()
    replay = create(client, owner, key=key)
    assert replay.status_code == 200 and replay.json()["id"] == first["id"]
    assert create(client, owner, sample(note="changed"), key).status_code == 409
    other = bearer(signed_in(client, "other_context"))
    assert create(client, other, key=key).status_code == 201
    assert client.delete(API + "/meals/" + first["id"], headers=owner).status_code == 204
    assert create(client, owner, key=key).json()["error"]["code"] == "idempotency_deleted"


def test_concurrent_create_replay_and_version_conflict(client, owner, app):
    key = "concurrent-save"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(TestClient(app), owner, key=key), range(2)))
    assert sorted(row.status_code for row in results) == [200, 201]
    meal = results[0].json()
    path = API + "/meals/" + meal["id"]

    def edit(note):
        return TestClient(app).patch(path, headers=owner, json={**sample(note=note), "version": 1})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["first", "second"]))
    assert sorted(row.status_code for row in results) == [200, 409]
    assert client.get(path, headers=owner).json()["version"] == 2


def test_database_lock_is_a_structured_retryable_error(client, owner, app):
    with app.state.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        blocked = create(client, owner)
        assert blocked.status_code == 503
        assert blocked.json()["error"]["code"] == "database_busy"
        assert blocked.headers["retry-after"] == "1"


def test_meal_and_items_roll_back_together(owner, app):
    def fail_second(_, __, item):
        if item.sort_order == 1:
            raise RuntimeError("forced test failure")

    event.listen(MealItem, "before_insert", fail_second)
    try:
        assert create(TestClient(app, raise_server_exceptions=False), owner, key="failed-write").status_code == 500
    finally:
        event.remove(MealItem, "before_insert", fail_second)
    with app.state.session_factory() as db:
        for model in (Meal, MealItem, MealRequest):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_multiple_photos_and_replacement_preserve_shared_reference(client, owner):
    first, second, third = [upload(client, owner).json()["id"] for _ in range(3)]
    assert first != second
    one = create(client, owner, sample(media_ids=[first, second])).json()
    assert [m["id"] for m in one["media"]] == [first, second]
    two = create(client, owner, sample(media_ids=[second])).json()
    assert client.get(API + "/calendar?month=2026-12", headers=owner).json()["days"][0]["representative_media_id"]
    edited = client.patch(API + "/meals/" + one["id"], headers=owner, json={**sample(media_ids=[third]), "version": 1})
    assert edited.status_code == 200
    assert client.delete(API + "/media/" + first, headers=owner).status_code == 204
    assert client.delete(API + "/media/" + second, headers=owner).status_code == 409
    assert client.delete(API + "/meals/" + two["id"], headers=owner).status_code == 204
    assert client.delete(API + "/media/" + second, headers=owner).status_code == 204
    assert client.get(API + "/media/" + third, headers=owner).status_code == 200


def test_account_isolation_anonymous_and_revoked(client, owner):
    photo = upload(client, owner).json()["id"]
    meal = create(client, owner, sample(media_ids=[photo])).json()["id"]
    other = bearer(signed_in(client, "other"))
    path = API + "/meals/" + meal
    photo_path = API + "/media/" + photo
    assert client.get(API + "/meals", headers=other).json()["total"] == 0
    for method, url, data in [
        ("GET", path, None), ("PATCH", path, {**sample(), "version": 1}), ("DELETE", path, None),
        ("GET", photo_path, None), ("GET", photo_path + "/thumbnail", None), ("DELETE", photo_path, None),
    ]:
        blocked = client.request(method, url, json=data, headers=other)
        random_url = url.replace(meal if "/meals/" in url else photo, str(uuid4()))
        absent = client.request(method, random_url, json=data, headers=other)
        assert blocked.status_code == 404 and blocked.json() == absent.json()
        assert client.request(method, url, json=data).status_code == 401
    assert create(client, other, sample(media_ids=[photo])).status_code == 404
    assert client.post(API + "/auth/logout", headers={**owner, **BROWSER}).status_code == 204
    assert client.get(photo_path, headers=owner).status_code == 401


def test_restart_keeps_meals_and_original_files(client, owner, settings):
    asset = upload(client, owner).json()["id"]
    meal = create(client, owner, sample(media_ids=[asset])).json()
    with TestClient(create_app(settings)) as reopened:
        refreshed = login(reopened)
        assert refreshed.status_code == 200
        assert reopened.get(API + "/meals/" + meal["id"], headers=bearer(refreshed)).json()["media"][0]["id"] == asset
        assert reopened.get(API + "/media/" + asset, headers=bearer(refreshed)).status_code == 200
