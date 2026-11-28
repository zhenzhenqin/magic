from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from secrets import token_urlsafe

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text, update

from app.core.config import BACKEND_DIR, Settings
from app.core.database import utcnow
from app.core.security import ALGORITHM, AUDIENCE, COOKIE_NAME, ISSUER, token_hash
from app.main import create_app
from app.models import AuthSession, User
from tests.support import isolated_settings, migrate

API = "/api/v1"
ORIGIN = "http://127.0.0.1:5173"
BROWSER = {"Origin": ORIGIN, "X-FoodDiary-Intent": "browser"}
PASSWORD = "phase-two-fixture-Password"


def register(client, username="reader", password=PASSWORD, nickname="手账读者"):
    return client.post(API + "/auth/register", headers=BROWSER,
                       json={"username": username, "password": password, "nickname": nickname})


def login(client, username="reader", password=PASSWORD):
    return client.post(API + "/auth/login", headers=BROWSER, json={"username": username, "password": password})


def signed_in(client, username="reader"):
    assert register(client, username).status_code == 201
    result = login(client, username)
    assert result.status_code == 200
    return result


def bearer(response):
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def refresh_headers(token):
    return {**BROWSER, "Cookie": COOKIE_NAME + "=" + token}


def end_last_refresh(app, **fields):
    with app.state.session_factory.begin() as db:
        db.execute(update(AuthSession).values(**fields))


def test_health(client):
    assert client.get(API + "/health").json() == {"status": "ok"}


def test_ready(client):
    assert client.get(API + "/ready").json() == {"status": "ready"}


def test_readiness_rejects_unmigrated_database(settings):
    with TestClient(create_app(settings)) as unready:
        assert unready.get(API + "/health").status_code == 200
        result = unready.get(API + "/ready")
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "database_unavailable"


def test_empty_database_migrates_and_configures_sqlite(app):
    engine = app.state.engine
    assert {"alembic_version", "users", "user_settings", "auth_sessions"}.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009_meal_photo_display"
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert connection.scalar(text("PRAGMA busy_timeout")) == 5000


def test_registration_exposes_public_identity_only(client):
    result = register(client, "Reader ")
    assert result.status_code == 201
    data = result.json()
    assert data["username"] == "reader"
    assert data["public_id"].startswith("fd_") and len(data["public_id"]) == 35
    assert data["created_at"].endswith("Z")
    assert {"id", "password_hash", "password", "is_active"}.isdisjoint(data)


def test_duplicate_username_is_case_insensitive(client):
    assert register(client, "Reader").status_code == 201
    result = register(client, "READER")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "username_taken"


@pytest.mark.parametrize(("username", "password"), [("no space", PASSWORD), ("xy", PASSWORD), ("reader", "short"), ("reader", "x" * 129)])
def test_registration_validates_and_redacts_fields(client, username, password):
    result = register(client, username, password)
    assert result.status_code == 422
    assert result.json()["error"]["fields"]
    assert password not in result.text


def test_concurrent_duplicate_registration(app):
    def write(username):
        return register(TestClient(app), username).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ["reader", "READER"])) == [201, 409]
    with app.state.session_factory() as db:
        assert len(db.scalars(select(User)).all()) == 1


def test_password_is_argon2id_not_plaintext(client, app):
    assert register(client).status_code == 201
    with app.state.session_factory() as db:
        stored = db.scalar(select(User.password_hash))
        assert stored.startswith("$argon2id$")
        assert PASSWORD not in stored
        assert app.state.passwords.hasher.verify(stored, PASSWORD)


def test_login_cookie_and_hashed_refresh_credential(client, app):
    response = signed_in(client)
    cookie = response.headers["set-cookie"]
    for attribute in ["HttpOnly", "SameSite=strict", "Path=/api/v1/auth", "Max-Age=", "expires="]:
        assert attribute in cookie
    assert "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"
    token = client.cookies.get(COOKIE_NAME)
    assert token not in response.text
    with app.state.session_factory() as db:
        assert db.scalar(select(AuthSession.refresh_token_hash)) == token_hash(token)


def test_login_error_does_not_disclose_account_existence(client):
    assert register(client).status_code == 201
    known = login(client, "reader", "incorrect")
    missing = login(client, "unknown", "incorrect")
    assert known.status_code == missing.status_code == 401
    assert known.json() == missing.json()


@pytest.mark.parametrize(("method", "path"), [("GET", "/users/me"), ("PATCH", "/users/me"), ("GET", "/users/me/settings"), ("PATCH", "/users/me/settings")])
def test_protected_routes_need_auth(client, method, path):
    result = client.request(method, API + path, json={"nickname": "set"} if method == "PATCH" else None)
    assert result.status_code == 401
    assert result.headers["www-authenticate"] == "Bearer"


def test_read_and_edit_own_profile(client):
    headers = bearer(signed_in(client))
    assert client.get(API + "/users/me", headers=headers).json()["nickname"] == "手账读者"
    result = client.patch(API + "/users/me", headers=headers, json={"nickname": "新昵称"})
    assert result.status_code == 200
    assert result.json()["nickname"] == "新昵称"


def test_protected_fields_and_other_user_cannot_be_modified(client):
    first = signed_in(client, "reader_a")
    second = signed_in(client, "reader_b")
    other = second.json()["user"]["public_id"]
    for path, data in [
        ("/users/me", {"nickname": "stolen", "user_id": other, "is_active": False}),
        ("/users/me/settings", {"timezone": "UTC", "user_id": other}),
    ]:
        assert client.patch(API + path, headers=bearer(first), json=data).status_code == 422
    assert client.patch(API + "/users/" + other, headers=bearer(first), json={"nickname": "stolen"}).status_code == 404
    assert client.get(API + "/users/me", headers=bearer(second)).json()["nickname"] == "手账读者"
    assert client.get(API + "/users/me/settings", headers=bearer(second)).json()["timezone"] == "Asia/Shanghai"


def test_preferences_partial_update_and_validation(client):
    headers = bearer(signed_in(client))
    changed = client.patch(API + "/users/me/settings", headers=headers, json={"timezone": "UTC", "show_calories": False})
    assert changed.status_code == 200
    assert changed.json()["show_calories"] is False and changed.json()["show_nutrition"] is True
    for data in [{"timezone": "unknown/zone"}, {"timezone": None}, {"show_nutrition": "false"}]:
        assert client.patch(API + "/users/me/settings", headers=headers, json=data).status_code == 422


def test_access_token_expiry_can_refresh(client, app, monkeypatch):
    import app.core.security as security

    now = utcnow()
    with monkeypatch.context() as patch:
        patch.setattr(security, "utcnow", lambda: now - timedelta(hours=1))
        result = signed_in(client)
    assert client.get(API + "/users/me", headers=bearer(result)).status_code == 401
    renewed = client.post(API + "/auth/refresh", headers=BROWSER)
    assert renewed.status_code == 200
    assert client.get(API + "/users/me", headers=bearer(renewed)).status_code == 200


def test_refresh_rotates_and_old_token_is_rejected_without_cookie_change(client, app):
    signed_in(client)
    previous = client.cookies.get(COOKIE_NAME)
    rotated = client.post(API + "/auth/refresh", headers=BROWSER)
    assert rotated.status_code == 200
    assert client.cookies.get(COOKIE_NAME) != previous
    replay = TestClient(app).post(API + "/auth/refresh", headers=refresh_headers(previous))
    assert replay.status_code == 409
    assert "set-cookie" not in replay.headers
    assert client.get(API + "/users/me", headers=bearer(rotated)).status_code == 200


def test_two_concurrent_refreshes_have_exactly_one_winner(client, app):
    signed_in(client)
    old = client.cookies.get(COOKIE_NAME)

    def rotate(_):
        return TestClient(app).post(API + "/auth/refresh", headers=refresh_headers(old))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(rotate, range(2)))
    assert sorted(result.status_code for result in responses) == [200, 409]
    winner = next(result for result in responses if result.status_code == 200)
    assert client.get(API + "/users/me", headers=bearer(winner)).status_code == 200


def test_repeated_old_cookie_replay_revokes_session_after_grace(client, app):
    signed_in(client)
    old = client.cookies.get(COOKIE_NAME)
    winner = client.post(API + "/auth/refresh", headers=BROWSER)
    end_last_refresh(app, last_used_at=utcnow() - timedelta(seconds=30))
    assert TestClient(app).post(API + "/auth/refresh", headers=refresh_headers(old)).status_code == 401
    assert client.get(API + "/users/me", headers=bearer(winner)).status_code == 401
    assert client.post(API + "/auth/refresh", headers=BROWSER).status_code == 401


def test_expired_refresh_is_denied(client, app):
    result = signed_in(client)
    end_last_refresh(app, expires_at=utcnow() - timedelta(seconds=1))
    assert client.post(API + "/auth/refresh", headers=BROWSER).status_code == 401
    assert client.get(API + "/users/me", headers=bearer(result)).status_code == 401


def test_logout_revokes_immediately_and_clears_cookie(client):
    initial = signed_in(client)
    response = client.post(API + "/auth/logout", headers={**BROWSER, **bearer(initial)})
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.cookies.get(COOKIE_NAME) is None
    assert client.get(API + "/users/me", headers=bearer(initial)).status_code == 401
    assert client.post(API + "/auth/refresh", headers=BROWSER).status_code == 401


def test_server_revocation_denies_existing_access_token(client, app):
    result = signed_in(client)
    end_last_refresh(app, revoked_at=utcnow())
    assert client.get(API + "/users/me", headers=bearer(result)).status_code == 401


def test_modified_or_wrong_audience_access_is_denied(client, app):
    token = signed_in(client).json()["access_token"]
    head, body, signature = token.split(".")
    tampered = ".".join([head, body, ("A" if signature[0] != "A" else "B") + signature[1:]])
    secret = app.state.settings.jwt_secret.get_secret_value()
    claims = jwt.decode(token, secret, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    claims["aud"] = "other-app"
    wrong_audience = jwt.encode(claims, secret, algorithm=ALGORITHM)
    for invalid in [tampered, wrong_audience]:
        assert client.get(API + "/users/me", headers={"Authorization": "Bearer " + invalid}).status_code == 401


def test_login_rate_limit(client, settings):
    settings.login_attempts = 2
    assert login(client).status_code == 401
    assert login(client).status_code == 401
    limited = login(client)
    assert limited.status_code == 429 and limited.headers["retry-after"]


def test_untrusted_origins_and_missing_intent_are_rejected(client):
    bad = client.post(API + "/auth/refresh", headers={"Origin": "https://foreign.example", "X-FoodDiary-Intent": "browser"})
    assert bad.status_code == 403 and "access-control-allow-origin" not in bad.headers
    assert client.post(API + "/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-fooddiary-intent"}
    allowed = client.options(API + "/auth/refresh", headers={**preflight, "Origin": ORIGIN})
    blocked = client.options(API + "/auth/refresh", headers={**preflight, "Origin": "https://foreign.example"})
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert blocked.status_code == 400


def test_persistence_across_app_restart(settings):
    migrate(settings)
    with TestClient(create_app(settings)) as first:
        profile = register(first, username="persisted").json()
    with TestClient(create_app(settings)) as second:
        restored = login(second, username="persisted")
        assert restored.status_code == 200
        assert restored.json()["user"]["public_id"] == profile["public_id"]


def test_testing_never_targets_project_development_db(settings):
    assert not settings.db_url.database.startswith(BACKEND_DIR.as_posix())
    with pytest.raises(ValueError):
        isolated_settings(BACKEND_DIR / "data" / "dev-test.db")


def test_production_uses_https_and_secure_cookie(settings):
    raw = settings.model_dump()
    raw.update(app_env="production", app_origins=["https://food.example"], public_registration=True)
    config = Settings(_env_file=None, **raw)
    migrate(config)
    with TestClient(create_app(config), base_url="https://food.example") as production:
        headers = {**BROWSER, "Origin": "https://food.example"}
        payload = {"username": "prod_test", "password": PASSWORD, "nickname": "测试"}
        assert production.post(API + "/auth/register", headers=headers, json=payload).status_code == 201
        result = production.post(API + "/auth/login", headers=headers, json={"username": payload["username"], "password": PASSWORD})
        assert "Secure" in result.headers["set-cookie"]
    for overrides in [{"jwt_secret": "replace-me-" + token_urlsafe(32)}, {"app_origins": [ORIGIN]}]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **{**raw, **overrides})
