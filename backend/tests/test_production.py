from contextlib import closing
from hashlib import sha256
from os import environ
from pathlib import Path
from secrets import token_urlsafe
from shutil import copyfile
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app import maintenance
from app import main
from app.core.config import Settings
from app.core.security import COOKIE_NAME
from app.main import create_app
from app.schemas import Registration
from app.services import auth
from app.services.sticker_worker import StickerWorker
from tests.support import migrate
from tests.test_diary import create, sample
from tests.test_friend_sharing import Peer, connect, media, route, update
from tests.test_identity import API, PASSWORD, bearer, signed_in
from tests.test_stickers_catalog import job, put, queue

HTTPS = "https://food.example"
BROWSER = {"Origin": HTTPS, "X-FoodDiary-Intent": "browser"}


def production(settings, **overrides):
    return Settings(_env_file=None, **(settings.model_dump() | {"app_env": "production", "app_origins": [HTTPS]} | overrides))


@pytest.mark.parametrize(("overrides", "message"), [
    ({"app_origins": ["http://food.example"]}, "require HTTPS"),
    ({"app_origins": ["https://food.example:*"]}, "port"),
    ({"app_origins": ["https://food.example/path"]}, "without paths"),
    ({"app_origins": ["https://food.example:443@other.example"]}, "without paths"),
    ({"database_url": "sqlite:///relative.db"}, "absolute SQLite"),
    ({"media_dir": "relative"}, "absolute private"),
    ({"ai_provider": "fake"}, "fake AI"),
    ({"sticker_provider": "fake"}, "fake sticker"),
])
def test_production_rejects_invalid_configuration(settings, overrides, message):
    with pytest.raises(ValidationError, match=f"(?i){message}"):
        production(settings, **overrides)


def provision(app, username):
    with app.state.session_factory() as db:
        return auth.register(db, Registration(username=username, nickname=username, password=PASSWORD), app.state.passwords).public_id


def login_https(client, username):
    response = client.post(API + "/auth/login", headers=BROWSER, json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response


def assert_private(response, expected):
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"


def test_production_closed_registration_csrf_private_image_and_shared_cache(settings):
    settings = production(settings)
    migrate(settings)
    app = create_app(settings)
    owner, viewer = provision(app, "prod_owner"), provision(app, "prod_viewer")
    with TestClient(app, base_url=HTTPS) as client:
        body = {"username": "prod_denied", "password": PASSWORD, "nickname": "closed"}
        denied = client.post(API + "/auth/register", headers=BROWSER, json=body)
        assert_private(denied, 403)
        assert denied.json()["error"]["code"] == "registration_closed"
        for headers, code in (({"Origin": HTTPS}, "csrf_check_failed"), ({"Origin": "https://other.example"}, "untrusted_origin")):
            rejected = client.post(API + "/auth/login", headers=headers, json=body)
            assert_private(rejected, 403)
            assert rejected.json()["error"]["code"] == code
        result = login_https(client, "prod_owner")
        assert_private(result, 200)
        cookie = result.headers["set-cookie"]
        assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=strict"))
        a, b = Peer(owner, bearer(result)), Peer(viewer, bearer(login_https(client, "prod_viewer")))
        photo = put(client, a.headers)
        entry = create(client, a.headers, sample(media_ids=[photo])).json()
        connect(client, a, b)
        update(client, a, b, records=True, photos=True)
        assert_private(client.get(API + "/media/" + photo, headers=a.headers), 200)
        assert_private(client.get(API + "/media/" + photo, headers=b.headers), 404)
        assert_private(client.get(route(a, "/meals/" + entry["id"]), headers=b.headers), 200)
        assert_private(media(client, b, a, photo, "/thumbnail", meal_id=entry["id"]), 200)
        assert_private(media(client, b, a, photo, "/sticker", meal_id=entry["id"]), 404)
        assert_private(client.get(API + "/friends", headers={"Origin": "https://other.example"}), 401)
        assert "access-control-allow-origin" not in client.get(API + "/health", headers={"Origin": "https://other.example"}).headers
        assert client.get("/openapi.json").status_code == 404


def ledger(path):
    with closing(maintenance.readonly(path)) as db:
        return dict(db.execute("SELECT provider,spent FROM ai_call_budgets"))


def test_backup_restore_keeps_media_relationships_and_ledger_settings(client, app, settings, tmp_path, monkeypatch):
    settings.sticker_enabled = True
    settings.sticker_provider = "fake"
    if model := environ.get("FOODDIARY_RESTORE_REAL_MODEL"):
        settings.sticker_model_dir = Path(model)
        settings.sticker_provider = "onnx"
    worker = StickerWorker(settings, app.state.session_factory)
    with_worker = []
    for name in ("safe_owner", "safe_viewer"):
        session = signed_in(client, name)
        with_worker.append(Peer(session.json()["user"]["public_id"], bearer(session)))
    a, b = with_worker
    old_cookie = client.cookies.get(COOKIE_NAME)
    worker.heartbeat()
    photo = put(client, a.headers)
    task = queue(client, a.headers, photo)
    try:
        assert worker.run_once() and job(client, a.headers, task)["status"] == "succeeded"
    finally:
        worker.close()
    visit = create(client, a.headers, sample(media_ids=[photo])).json()
    connect(client, a, b)
    update(client, a, b, records=True, names=True, stickers=True)
    assert_private(media(client, b, a, photo, "/sticker", meal_id=visit["id"]), 200)
    expected = {suffix: client.get(API + "/media/" + photo + suffix, headers=a.headers).content
                for suffix in ("", "/thumbnail", "/sticker", "/sticker/thumbnail", "/sticker/cutout")}
    db_path = Path(settings.db_url.database).resolve()
    backup = tmp_path / "daily"
    restored = tmp_path / "restore"
    with closing(sqlite3.connect(db_path)) as writer:
        writer.execute("UPDATE ai_call_budgets SET spent=7 WHERE provider='deepseek'")
        writer.commit()
        assert (db_path.parent / (db_path.name + "-wal")).exists()
        maintenance.backup(db_path, settings.media_root, backup, 0, "fixture")
    recovery = maintenance.verify(backup)
    assert len(recovery["media"]) == 5 and ledger(backup / maintenance.DATABASE)["deepseek"] == 7
    with pytest.raises(FileExistsError):
        maintenance.backup(db_path, settings.media_root, backup, 0, "fixture")
    monkeypatch.setattr(maintenance, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="disk space"):
        maintenance.restore(backup, restored, 0)
    assert not restored.exists()
    monkeypatch.undo()
    maintenance.restore(backup, restored, 0)
    assert ledger(restored / "data" / maintenance.DATABASE)["deepseek"] == 7
    assert ledger(db_path)["deepseek"] == 7
    restored_config = production(settings, database_url="sqlite:///" + (restored / "data" / maintenance.DATABASE).as_posix(),
                                 media_dir=restored / "media", sticker_provider="onnx", sticker_enabled=False)
    assert not restored_config.ai_enabled and "AI_ENABLED=false" in (restored / "ISOLATED.env").read_text()
    with TestClient(create_app(restored_config), base_url=HTTPS) as reopened:
        assert_private(reopened.get(API + "/users/me", headers=b.headers), 401)
        refreshed = reopened.post(API + "/auth/refresh", headers={**BROWSER, "Cookie": f"{COOKIE_NAME}={old_cookie}"})
        assert_private(refreshed, 401)
        fresh_a = Peer(a.id, bearer(login_https(reopened, "safe_owner")))
        fresh_b = Peer(b.id, bearer(login_https(reopened, "safe_viewer")))
        saved = reopened.get(API + "/meals/" + visit["id"], headers=fresh_a.headers)
        assert saved.json()["items"][0]["food_name"] == visit["items"][0]["food_name"]
        relation = reopened.get(route(a, "/sharing"), headers=fresh_b.headers).json()
        assert relation["person"]["public_id"] == a.id and not any(relation["incoming"]["permissions"].values())
        assert_private(media(reopened, fresh_b, fresh_a, photo, "/sticker", meal_id=visit["id"]), 404)
        for suffix, content in expected.items():
            file = reopened.get(API + "/media/" + photo + suffix, headers=fresh_a.headers)
            assert_private(file, 200)
            assert file.content == content
        assert update(reopened, fresh_a, fresh_b, records=True, stickers=True).status_code == 200
        assert_private(media(reopened, fresh_b, fresh_a, photo, "/sticker", meal_id=visit["id"]), 200)
    damaged = backup / "media" / next(iter(recovery["media"]))
    damaged.write_bytes(damaged.read_bytes() + b"damage")
    with pytest.raises(ValueError, match="media checksum"):
        maintenance.restore(backup, tmp_path / "bad", 0)
    assert not (tmp_path / "bad").exists()


def test_migration_candidate_failure_preserves_live_release(settings, tmp_path, monkeypatch):
    migrate(settings, "0007_stickers_catalog")
    live = Path(settings.db_url.database).resolve()
    original = sha256(live.read_bytes()).digest()
    candidate = tmp_path / ".candidate-release.db"
    copyfile(live, candidate)
    monkeypatch.setenv("JWT_SECRET", token_urlsafe(48))
    monkeypatch.setenv("APP_ENV", "test")
    real = maintenance.command.upgrade

    def interrupted(config, _head):
        config.attributes["connection"].exec_driver_sql("CREATE TABLE partial_migration (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration interrupted")

    monkeypatch.setattr(maintenance.command, "upgrade", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        maintenance.migrate_candidate(candidate)
    with pytest.raises(ValueError, match="isolated"):
        maintenance.migrate_candidate(live)
    assert sha256(live.read_bytes()).digest() == original
    with closing(maintenance.readonly(live)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0007_stickers_catalog",)
    monkeypatch.setattr(maintenance.command, "upgrade", real)
    good = tmp_path / f".candidate-{uuid4().hex}.db"
    copyfile(live, good)
    maintenance.migrate_candidate(good)
    with closing(maintenance.readonly(good)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0008_friend_sharing",)


def test_running_release_identity_follows_the_release_at_start(settings, tmp_path, monkeypatch):
    settings = production(settings)
    migrate(settings)
    marker = tmp_path / "REVISION"
    marker.write_text("1" * 40)
    monkeypatch.setattr(main, "BACKEND_DIR", tmp_path / "backend")
    app = main.create_app(settings)
    marker.write_text("2" * 40)
    with TestClient(app, base_url=HTTPS) as client:
        for path in ("health", "ready"):
            assert client.get(API + "/" + path).headers["x-fooddiary-revision"] == "1" * 40
        assert "x-fooddiary-revision" not in client.get(API + "/friends").headers


def test_daily_retention_requires_latest_verified_point_and_preserves_other_data(settings, tmp_path):
    migrate(settings)
    database = Path(settings.db_url.database).resolve()
    settings.media_root.mkdir()
    points = [tmp_path / f"daily-2026112{day}T043000-911" for day in range(4)]
    for point in points:
        maintenance.backup(database, settings.media_root, point, 0, "retention-fixture")
    release = tmp_path / "release-20261120T043000-911"
    release.mkdir()
    unrelated = tmp_path / "daily-20261119T043000-911"
    unrelated.mkdir()
    with pytest.raises(ValueError, match="latest"):
        maintenance.retain_daily(tmp_path, points[-2])
    assert all(point.exists() for point in points)
    maintenance.retain_daily(tmp_path, points[-1])
    assert not points[0].exists() and all(point.exists() for point in points[1:])
    assert release.exists() and unrelated.exists()
