from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.models.sharing import Friendship, MediaWriteReservation, SharePermission
from app.services import friends, storage
from app.services.sticker_worker import StickerWorker
from tests.test_ai_jobs import JOBS, new_job
from tests.test_diary import create, sample
from tests.test_identity import API, bearer, signed_in
from tests.test_stickers_catalog import job, put, queue

FRIENDS = API + "/friends"
TODAY = "2027-01-01"


@dataclass(frozen=True)
class Peer:
    id: str
    headers: dict[str, str] = field(repr=False)


@pytest.fixture
def peers(client, monkeypatch):
    monkeypatch.setattr(friends, "utcnow", lambda: datetime(2026, 12, 31, 17, tzinfo=UTC))
    return tuple(Peer(id=response.json()["user"]["public_id"], headers=bearer(response))
                 for response in (signed_in(client, "sharing_a"), signed_in(client, "sharing_b"), signed_in(client, "sharing_c")))


def route(person, suffix):
    return FRIENDS + "/" + person.id + suffix


def send(client, sender, receiver):
    return client.post(FRIENDS + "/requests", headers=sender.headers, json={"public_id": receiver.id})


def respond(client, actor, request, action):
    return client.post(FRIENDS + "/requests/" + request + "/" + action, headers=actor.headers)


def connect(client, a, b):
    request = send(client, a, b)
    assert request.status_code == 202, request.text
    assert respond(client, b, request.json()["id"], "accept").status_code == 200
    return client.get(route(b, "/sharing"), headers=a.headers).json()


def update(client, owner, viewer, current=None, scope=None, confirm_start=None, **flags):
    path = route(viewer, "/sharing")
    current = current or client.get(path, headers=owner.headers).json()
    return client.put(path, headers=owner.headers, json={
        "relationship_id": current["relationship_id"], "version": current["outgoing"]["version"],
        "history_scope": scope, "confirm_history_start": confirm_start, "permissions": flags,
    })


def save(client, owner, day=TODAY, **fields):
    result = create(client, owner.headers, sample(local_date=day, **fields))
    assert result.status_code == 201, result.text
    return result.json()


def media(client, viewer, owner, image, suffix="", **context):
    return client.get(route(owner, "/media/" + image + suffix), headers=viewer.headers, params=context)


def test_friend_request_lifecycle_rate_and_private_lookup(client, peers, app):
    a, b, c = peers
    lookup = client.get(FRIENDS + "/lookup", headers=a.headers, params={"public_id": b.id})
    assert lookup.status_code == 200 and set(lookup.json()) == {"nickname", "public_id"}
    assert client.get(FRIENDS + "/lookup", headers=a.headers, params={"public_id": b.id[:-1]}).status_code == 422
    assert send(client, a, a).status_code == 422
    first = send(client, a, b).json()
    assert send(client, a, b).json()["id"] == first["id"]
    assert send(client, b, a).json()["direction"] == "incoming"
    assert respond(client, c, first["id"], "accept").status_code == 404
    assert respond(client, a, first["id"], "accept").status_code == 404
    assert respond(client, b, first["id"], "cancel").status_code == 404
    assert respond(client, b, first["id"], "reject").json()["status"] == "rejected"
    assert send(client, a, b).status_code == 429
    reverse = send(client, b, a).json()
    assert reverse["id"] != first["id"]
    assert respond(client, b, reverse["id"], "cancel").json()["status"] == "cancelled"
    assert respond(client, a, reverse["id"], "accept").status_code == 409
    app.state.settings.friend_lookup_attempts = 1
    assert client.get(FRIENDS + "/lookup", headers=c.headers, params={"public_id": a.id}).status_code == 200
    assert client.get(FRIENDS + "/lookup", headers=c.headers, params={"public_id": b.id}).status_code == 429
    app.state.settings.friend_request_attempts = 1
    assert send(client, c, a).status_code == 202
    assert send(client, c, b).status_code == 429


def test_crossed_requests_concurrent_accept_and_remove(app, client, peers):
    a, b, c = peers
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(send, TestClient(app), source, target) for source, target in ((a, b), (b, a))]
        responses = [future.result() for future in futures]
        assert [result.status_code for result in responses] == [202, 202]
        first, second = [result.json() for result in responses]
        assert first["id"] == second["id"] and {first["direction"], second["direction"]} == {"incoming", "outgoing"}
        receiver = b if first["direction"] == "outgoing" else a
        replies = list(pool.map(lambda _: respond(TestClient(app), receiver, first["id"], "accept"), range(2)))
        assert all(reply.json()["status"] == "accepted" for reply in replies)
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(Friendship)) == 1
        relation = client.get(route(b, "/sharing"), headers=a.headers).json()
        assert not any(relation["outgoing"]["permissions"].values())
        assert not any(relation["incoming"]["permissions"].values())
        assert client.get(route(a, "/sharing"), headers=c.headers).status_code == 404
        edits = list(pool.map(lambda _: update(TestClient(app), a, b, relation, records=True), range(2)))
        assert sorted(result.status_code for result in edits) == [200, 409]
        change = lambda _: TestClient(app).delete(route(b, ""), headers=a.headers,
                                                  params={"relationship_id": relation["relationship_id"]})
        assert [result.status_code for result in pool.map(change, range(2))] == [204, 204]
    assert client.get(route(a, "/meals"), headers=b.headers, params={"date": TODAY}).status_code == 404
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(SharePermission)) == 0
    new = connect(client, a, b)
    assert new["relationship_id"] != relation["relationship_id"]
    assert new["outgoing"]["history_start"] is None
    assert update(client, a, b, relation, records=True).status_code == 404
    assert client.delete(route(b, ""), headers=a.headers,
                         params={"relationship_id": relation["relationship_id"]}).status_code == 404


def test_direction_fields_zero_and_missing_are_distinct(client, peers):
    a, b, c = peers
    connect(client, a, b)
    entry = save(client, a, items=[
        {"food_name": "共享米饭", "category": "主食", "note": "私人明细", "calories_kcal": 0, "weight_g": 50, "protein_g": 1},
        {"food_name": "花茶"},
    ], note="私人餐次")
    item_path = route(a, "/meals/" + entry["id"])
    assert client.get(item_path, headers=b.headers).status_code == 404
    assert update(client, a, b, records=True).status_code == 200
    visible = client.get(item_path, headers=b.headers).json()
    assert set(visible) == {"id", "local_date", "local_time", "meal_type"}
    assert client.get(item_path, headers=c.headers).status_code == 404
    assert client.get(API + "/meals/" + entry["id"], headers=b.headers).status_code == 404
    assert client.patch(item_path, headers=b.headers, json=sample()).status_code == 405
    assert client.get(route(b, "/meals"), headers=a.headers, params={"date": TODAY}).status_code == 404
    assert update(client, b, a, records=True, notes=True).status_code == 200
    assert set(client.get(item_path, headers=b.headers).json()) == set(visible)
    assert update(client, a, b, records=True, names=True, photos=True, stickers=True, catalog=True,
                  calories=True, nutrition=True, notes=True, history=True).status_code == 200
    exposed = client.get(item_path, headers=b.headers).json()
    assert exposed["note"] == "私人餐次" and exposed["media"] == []
    first, second = exposed["items"]
    assert first["food_name"] == "共享米饭" and first["category"] == "主食" and first["note"] == "私人明细"
    assert first["calories_kcal"] == 0 and first["weight_g"] == 50 and first["estimated"] is False
    assert second["calories_kcal"] is None and "estimated" not in second
    assert {"source", "ai_provider", "ai_candidate_id", "id"}.isdisjoint(first)
    summary = client.get(route(a, "/statistics/daily"), headers=b.headers, params={"date": TODAY}).json()
    assert summary["nutrition"]["calories_kcal"] == dict(value=0, known_items=1, complete=False, estimated=False)
    assert summary["nutrition"]["fat_g"]["value"] is None
    update(client, a, b, records=True, calories=True)
    scoped = client.get(item_path, headers=b.headers).json()
    assert set(scoped["items"][0]) == {"calories_kcal", "estimated"}
    assert {"note", "media"}.isdisjoint(scoped)
    assert client.get(route(a, "/catalog"), headers=b.headers).status_code == 404


def test_owner_clock_fixed_history_scopes_date_edits_and_private_catalog(client, peers, monkeypatch):
    a, b, _ = peers
    connect(client, a, b)
    settings_path = API + "/users/me/settings"
    assert client.patch(settings_path, headers=a.headers, json={"timezone": "Asia/Tokyo"}).status_code == 200
    assert client.patch(settings_path, headers=b.headers, json={"timezone": "America/New_York"}).status_code == 200
    past_photo = put(client, a.headers)
    old = save(client, a, "2026-12-30", items=[{"food_name": "米饭", "category": "主食"}], media_ids=[past_photo])
    new = save(client, a, TODAY, items=[{"food_name": "米饭", "category": "主食"}, {"food_name": "茶"}])
    own_index = client.get(API + "/catalog", headers=a.headers).json()["items"]
    own_food = next(item for item in own_index if item["display_name"] == "米饭")
    edited = client.patch(API + "/catalog/" + own_food["id"], headers=a.headers,
                          json={"display_name": "不应共享的私有别名", "is_favorite": True})
    assert edited.status_code == 200, edited.text
    flags = dict(records=True, catalog=True, names=True, photos=True, history=True)
    grant = update(client, a, b, **flags).json()
    assert grant["outgoing"]["history_start"] == TODAY
    result = client.get(route(a, "/catalog"), headers=b.headers)
    assert result.status_code == 200, result.text
    gallery = result.json()
    assert gallery["total"] == 2 and "私有别名" not in result.text
    rice = next(item for item in gallery["items"] if item["name"] == "米饭")
    assert {"cover", "favorite", "display_name"}.isdisjoint(rice)
    assert (rice["occurrences"], rice["first_eaten"]) == (1, TODAY)
    assert not client.get(route(a, "/calendar?month=2026-12"), headers=b.headers).json()["days"]
    assert media(client, b, a, past_photo, catalog_id=rice["id"]).status_code == 404
    narrowed = client.get(route(a, "/catalog/" + rice["id"] + "/history"), headers=b.headers)
    assert [item["id"] for item in narrowed.json()["items"]] == [new["id"]]
    assert update(client, a, b, scope="week", **flags).json()["outgoing"]["history_start"] == "2026-12-26"
    assert update(client, a, b, scope="month", **flags).json()["outgoing"]["history_start"] == "2026-12-03"
    assert update(client, a, b, scope="all", **flags).json()["outgoing"]["history_start"] is None
    needs_confirmation = update(client, a, b, nutrition=True, **flags)
    assert needs_confirmation.status_code == 422 and needs_confirmation.json()["error"]["code"] == "history_choice_required"
    clock = datetime(2027, 1, 2, 16, tzinfo=UTC)
    monkeypatch.setattr(friends, "utcnow", lambda: clock)
    assert update(client, a, b, **flags).json()["outgoing"]["history_start"] is None
    scoped = client.get(route(a, "/catalog/" + rice["id"]), headers=b.headers).json()
    assert (scoped["first_eaten"], scoped["occurrences"], scoped["cover"]["id"]) == ("2026-12-30", 2, past_photo)
    moved = client.patch(API + "/meals/" + old["id"], headers=a.headers,
                         json={**sample(local_date="2027-01-05", media_ids=[past_photo]), "version": old["version"]})
    assert moved.status_code == 200, moved.text
    grant = update(client, a, b, scope="today", **flags).json()
    assert grant["outgoing"]["history_start"] == "2027-01-03"
    assert client.get(route(a, "/meals/" + old["id"]), headers=b.headers).status_code == 200
    assert client.get(route(a, "/meals/" + new["id"]), headers=b.headers).status_code == 404
    response = client.delete(route(b, "/sharing"), headers=a.headers, params={
        "version": grant["outgoing"]["version"], "relationship_id": grant["relationship_id"],
    })
    assert response.status_code == 200 and not any(response.json()["outgoing"]["permissions"].values())
    reopened = update(client, a, b, **flags).json()
    assert reopened["outgoing"]["history_start"] == "2027-01-03"
    update(client, a, b, catalog=True)
    invisible = client.get(route(a, "/catalog"), headers=b.headers).json()
    assert invisible == {"names_shared": False, "items": [], "page": 1, "limit": 24}


def test_media_needs_context_live_reference_permissions_and_existing_sticker(client, app, peers):
    a, b, c = peers
    connect(client, a, b)
    app.state.settings.sticker_enabled = True
    app.state.settings.sticker_provider = "fake"
    worker = StickerWorker(app.state.settings, app.state.session_factory)
    worker.heartbeat()
    image = put(client, a.headers)
    waiting = put(client, a.headers)
    draft = put(client, a.headers)
    outsider = put(client, c.headers)
    identifier = queue(client, a.headers, image)
    assert worker.run_once() and job(client, a.headers, identifier)["status"] == "succeeded"
    entry = save(client, a, media_ids=[image, waiting])
    second = save(client, a, "2026-12-29", media_ids=[image])
    update(client, a, b, records=True, names=True, stickers=True, catalog=True)
    context = {"meal_id": entry["id"]}
    for variant in ("/sticker", "/sticker/thumbnail"):
        result = media(client, b, a, image, variant, **context)
        assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
        for unrelated in (waiting, draft, outsider):
            assert media(client, b, a, unrelated, variant, **context).status_code == 404
    for variant in ("", "/thumbnail", "/sticker/cutout", "/cutout"):
        assert media(client, b, a, image, variant, **context).status_code == 404
    assert media(client, b, a, image, "/sticker").status_code == 404
    assert media(client, b, a, image, "/sticker", meal_id=second["id"]).status_code == 404
    assert media(client, c, a, image, "/sticker", **context).status_code == 404
    app.state.settings.ai_enabled = True
    app.state.settings.ai_provider = "fake"
    active = new_job(client, a.headers, [image], form_meal_id=entry["id"])
    assert active.status_code == 202, active.text
    assert media(client, b, a, image, "/sticker", **context).status_code == 404
    assert client.get(API + "/media/" + image + "/sticker", headers=a.headers).status_code == 200
    finished = client.post(JOBS + "/" + active.json()["id"] + "/cancel", headers=a.headers)
    assert finished.status_code == 200 and media(client, b, a, image, "/sticker", **context).status_code == 200
    update(client, a, b, catalog=True, names=True, stickers=True)
    cover = next(row for row in client.get(route(a, "/catalog"), headers=b.headers).json()["items"] if row["cover"]["id"] == image)
    assert cover["cover_whole_meal"] and "occurrences" not in cover
    assert media(client, b, a, image, "/sticker", catalog_id=cover["id"]).status_code == 200
    assert media(client, b, a, image, "/sticker", catalog_id="0" * 32).status_code == 404
    assert media(client, b, a, image, "/sticker", **context).status_code == 404
    assert client.get(route(a, "/catalog/" + cover["id"] + "/history"), headers=b.headers).status_code == 404
    update(client, a, b, records=True, photos=True)
    assert media(client, b, a, image, "/sticker", **context).status_code == 404
    for variant in ("", "/thumbnail"):
        assert media(client, b, a, image, variant, **context).status_code == 200
    replaced = client.patch(API + "/meals/" + entry["id"], headers=a.headers,
                            json={**sample(local_date=TODAY, media_ids=[waiting]), "version": entry["version"]})
    assert replaced.status_code == 200 and media(client, b, a, image, **context).status_code == 404
    assert media(client, b, a, waiting, **context).status_code == 200
    assert client.delete(API + "/meals/" + entry["id"], headers=a.headers, params={"version": 2}).status_code == 204
    assert media(client, b, a, waiting, **context).status_code == 404


def test_revocation_serializes_with_reads(app, client, peers):
    a, b, _ = peers
    connect(client, a, b)
    saved = save(client, a)
    assert update(client, a, b, records=True, notes=True).status_code == 200
    path = route(a, "/meals/" + saved["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(TestClient(app).get, path, headers=b.headers)
        revoke = pool.submit(update, TestClient(app), a, b)
        assert read.result().status_code in (200, 404)
        assert revoke.result().status_code == 200
    assert client.get(path, headers=b.headers).status_code == 404


@pytest.mark.parametrize("permission", ["photos", "stickers", "notes", "nutrition"])
def test_fixed_today_grant_requires_cross_day_confirmation(client, peers, monkeypatch, permission):
    a, b, _ = peers
    monkeypatch.setattr(friends, "utcnow", lambda: datetime(2026, 11, 1, 12, tzinfo=UTC))
    earlier = save(client, a, "2026-11-01", note="早先的备注")
    connect(client, a, b)
    grant = update(client, a, b, records=True, names=True).json()
    assert grant["outgoing"]["history_start"] == "2026-11-01"
    path = route(a, "/meals/" + earlier["id"])
    monkeypatch.setattr(friends, "utcnow", lambda: datetime(2026, 11, 28, 12, tzinfo=UTC))
    flags = {"records": True, "names": True, permission: True}
    for confirmation in (None, "2026-11-27"):
        warning = update(client, a, b, grant, confirm_start=confirmation, **flags)
        assert warning.status_code == 422 and warning.json()["error"]["code"] == "history_choice_required"
    assert not client.get(route(b, "/sharing"), headers=a.headers).json()["outgoing"]["permissions"][permission]
    assert "note" not in client.get(path, headers=b.headers).json()
    shared = update(client, a, b, grant, confirm_start="2026-11-01", **flags)
    assert shared.status_code == 200 and shared.json()["outgoing"]["history_start"] == "2026-11-01"
    if permission == "notes":
        assert client.get(path, headers=b.headers).json()["note"] == "早先的备注"
    rebased = update(client, a, b, scope="today", **flags)
    assert rebased.json()["outgoing"]["history_start"] == "2026-11-28"
    assert client.get(path, headers=b.headers).status_code == 404


def test_disk_reservations_and_low_free_upload(app, client, peers, monkeypatch):
    a, _, _ = peers
    settings = app.state.settings
    sessions = app.state.session_factory
    monkeypatch.setattr(storage, "disk_usage", lambda _: SimpleNamespace(free=settings.sticker_min_free_bytes + 120))
    with ThreadPoolExecutor(max_workers=2) as pool:
        def reserve(_):
            try:
                return storage.reserve_media_bytes(sessions, settings, 100)
            except storage.ApiError as failure:
                assert failure.status == 507
                return None
        first, second = list(pool.map(reserve, range(2)))
    assert bool(first) != bool(second)
    assert client.post(API + "/media/upload", headers=a.headers, files={"file": ("missing.jpg", b"x")}).status_code == 507
    storage.release_media_bytes(sessions, first or second)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MediaWriteReservation)) == 0


def test_diary_query_count_stays_bounded_for_a_page_with_photos(client, app, peers):
    a, b, _ = peers
    connect(client, a, b)
    image = put(client, a.headers)
    save(client, a, media_ids=[image])
    update(client, a, b, records=True, names=True, photos=True, calories=True, notes=True)
    path = route(a, "/meals")
    statements = []
    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.split()[0])
    event.listen(app.state.engine, "before_cursor_execute", record)
    try:
        assert client.get(path, headers=b.headers, params={"date": TODAY}).json()["total"] == 1
        small = len(statements)
        for index in range(19):
            save(client, a, media_ids=[image], local_time=f"12:{index:02}")
        statements.clear()
        result = client.get(path, headers=b.headers, params={"date": TODAY})
        assert len(result.json()["items"]) == 20
        assert len(statements) == small <= 10
    finally:
        event.remove(app.state.engine, "before_cursor_execute", record)
