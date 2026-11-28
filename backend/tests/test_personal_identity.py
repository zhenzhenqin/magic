import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.core.database import utcnow
from app.core.security import token_hash
from app.main import create_app
from app import maintenance
from app.models import User
from app.models.ai import AiJob, AiUsageLog
from app.models.identity import EmailChallenge, Invitation
from app.models.stickers import StickerJob
from app.services.ai_credentials import TemporaryCredentials
from app.services.ai_provider import FakeVisionProvider, ProviderError, simulated_balance
from app.services.ai_worker import AiWorker
from app.services.identity import create_invitation
from app.services.sticker_worker import RenderedSticker, StickerWorker
from tests.support import isolated_settings, migrate
from tests.test_ai_jobs import JOBS, new_job, photo
from tests.test_identity import API, BROWSER, PASSWORD, bearer, login, register, signed_in

CONNECTION = API + "/ai/connection"
SECURITY = API + "/users/me/security"
EMAIL = API + "/auth/email/"
TEST_A = "fd-test-alice12345"
TEST_B = "fd-test-bob678901"


@pytest.fixture
def byok(tmp_path):
    settings = isolated_settings(tmp_path / "byok-test.db", ai_enabled=True, ai_provider="fake", ai_byok_simulation=True,
                                 ai_api_key="unused-admin-fixture")
    migrate(settings)
    app = create_app(settings)
    # Start the worker explicitly so each test can observe credentials and control dispatch timing.
    client = TestClient(app)
    yield app, client
    client.close()
    app.state.engine.dispose()


def connect(client, headers, key):
    return client.put(CONNECTION, headers=headers, json={"api_key": key})


def scoped(app, observe, vault=None, *, unknown=False):
    class Unknown:
        async def analyze(self, images):
            raise ProviderError("ai_result_unknown")

    def provider(credential):
        observe[credential.owner] = credential.key.get_secret_value()
        return Unknown() if unknown else FakeVisionProvider()

    return AiWorker(app.state.settings, app.state.session_factory, FakeVisionProvider(),
                    vault=app.state.ai_credentials if vault is None else vault, scoped_provider=provider)


def test_calls_resolve_only_the_matching_users_secret_and_history_is_private(byok):
    app, client = byok
    a, b = (bearer(signed_in(client, name)) for name in ("alice_byok", "bob_byok"))
    first, second = photo(client, a), photo(client, b)
    assert new_job(client, a, [first]).json()["error"]["code"] == "ai_credential_required"
    assert not client.get(API + "/ai/capabilities", headers=b).json()["available"]
    response = connect(client, a, TEST_A)
    assert response.status_code == 200 and TEST_A not in response.text
    assert not client.get(CONNECTION, headers=b).json()["connected"]
    assert connect(client, b, TEST_B).status_code == 200
    observed = {}
    service = scoped(app, observed)
    jobs = [new_job(client, user, [identifier]).json()["id"] for user, identifier in ((a, first), (b, second))]
    for task in jobs:
        assert asyncio.run(service.process_once())
    with app.state.session_factory() as db:
        rows = {row.username: row.id for row in db.scalars(select(User))}
        assert observed == {rows["alice_byok"]: TEST_A, rows["bob_byok"]: TEST_B}
        ledger = db.scalars(select(AiUsageLog)).all()
        assert {row.user_id for row in ledger} == set(rows.values())
        assert len({row.credential_ref for row in ledger}) == 2
    for user in (a, b):
        state = client.get(CONNECTION, headers=user).json()
        assert state["total"] == state["today"] == 1
        assert state["input_tokens"] is None
    assert client.get(JOBS + "/" + jobs[0], headers=b).status_code == 404
    for file in app.state.settings.media_root.parent.glob("*.db*"):
        data = file.read_bytes()
        assert all(secret.encode() not in data for secret in (TEST_A, TEST_B, "unused-admin-fixture"))


@pytest.mark.parametrize("end", ["replace", "delete", "expiry", "restart", "logout", "switch"])
def test_disconnected_or_replaced_credentials_never_dispatch_old_jobs(byok, end):
    app, client = byok
    a = bearer(signed_in(client, "alice_byok"))
    assert connect(client, a, TEST_A).status_code == 200
    image = photo(client, a)
    identifier = new_job(client, a, [image]).json()["id"]
    vault = app.state.ai_credentials
    if end == "replace":
        assert connect(client, a, TEST_B).status_code == 200
    elif end == "delete":
        assert client.delete(CONNECTION, headers=a).status_code == 204
    elif end == "expiry":
        with app.state.session_factory() as db:
            job = db.get(AiJob, identifier)
            vault.connect(job.user_id, job.credential_session_id, vault.get(job.user_id, job.credential_session_id).key,
                          1, utcnow() - timedelta(seconds=1))
    elif end == "restart":
        vault = TemporaryCredentials()
    elif end == "logout":
        assert client.post(API + "/auth/logout", headers={**BROWSER, **a}).status_code == 204
    else:
        signed_in(client, "bob_byok")
    observed = {}
    assert not asyncio.run(scoped(app, observed, vault).process_once())
    assert not observed
    with app.state.session_factory() as db:
        assert db.get(AiJob, identifier).error_code == "ai_credential_expired"
        assert db.scalar(select(AiUsageLog.id)) is None


def test_unknown_attempt_is_counted_once_and_a_users_limit_can_pause_creation(byok):
    app, client = byok
    a = bearer(signed_in(client))
    assert connect(client, a, TEST_A).status_code == 200
    image = photo(client, a)
    key = uuid4().hex
    result = new_job(client, a, [image], key=key).json()
    assert asyncio.run(scoped(app, {}, unknown=True).process_once())
    assert new_job(client, a, [image], key=key).json()["id"] == result["id"]
    assert client.get(CONNECTION, headers=a).json()["unknown"] == 1
    assert client.patch(API + "/ai/preferences", headers=a, json={"daily_limit": 0}).status_code == 200
    assert new_job(client, a, [image]).status_code == 429


def test_balance_contract_uses_the_current_key_and_never_follows_redirects(byok, caplog):
    app, client = byok
    a = bearer(signed_in(client))
    assert connect(client, a, TEST_A).status_code == 200
    task = new_job(client, a, [photo(client, a)]).json()["id"]
    with app.state.session_factory() as db:
        job = db.get(AiJob, task)
        credential = app.state.ai_credentials.get(job.user_id, job.credential_session_id)
    requests = []

    def reject(request):
        requests.append((str(request.url), request.method, request.headers["authorization"]))
        return httpx.Response(307, headers={"location": "https://example.test"})

    with pytest.raises(ProviderError, match="ai_balance_unavailable"):
        simulated_balance(credential, httpx.MockTransport(reject))
    assert requests == [("https://api.deepseek.com/user/balance", "GET", "Bearer " + TEST_A)]
    assert TEST_A not in caplog.text
    assert TEST_A not in client.post(CONNECTION + "/balance", headers=a).text


def test_restore_cancels_old_jobs_and_never_rehydrates_a_temporary_key(byok, tmp_path):
    app, client = byok
    a = bearer(signed_in(client))
    assert connect(client, a, TEST_A).status_code == 200
    identifier = new_job(client, a, [photo(client, a)]).json()["id"]
    settings = app.state.settings
    source, target = tmp_path / "backup", tmp_path / "restored"
    maintenance.backup(Path(settings.db_url.database), settings.media_root, source, 0, "phase73-fixture")
    maintenance.restore(source, target, 0)
    recovered = isolated_settings(tmp_path / "restored-test.db", ai_enabled=True,
                                  ai_provider="fake", ai_byok_simulation=True)
    recovered.database_url = "sqlite:///" + (target / "data" / "fooddiary.db").as_posix()
    restored = create_app(recovered)
    with restored.state.session_factory() as db:
        job = db.get(AiJob, identifier)
        assert job.status == "cancelled" and job.error_code == "restored_job_cancelled"
        assert restored.state.ai_credentials.get(job.user_id, job.credential_session_id) is None
    restored.state.engine.dispose()


def test_production_never_uses_an_explicit_legacy_key(settings):
    production = Settings(_env_file=None, app_env="production", jwt_secret=token_urlsafe(48),
                          database_url=settings.database_url, media_dir=settings.media_dir,
                          app_origins=["https://food.example"], ai_enabled=True, ai_provider="deepseek",
                          ai_base_url="https://api.deepseek.com", ai_model="deepseek-flash",
                          ai_api_key="unused-admin-fixture", ai_deepseek_cumulative_limit=100)
    assert not production.ai_available


@pytest.fixture
def mailbox(tmp_path):
    settings = isolated_settings(tmp_path / "mail-test.db", email_mode="capture", email_code_secret=token_urlsafe(48))
    migrate(settings)
    with TestClient(create_app(settings)) as client:
        yield client


def ticket(client, email="cook@example.test", purpose="register", invitation=None):
    result = client.post(EMAIL + "code", headers=BROWSER, json={"email": email, "purpose": purpose, "invitation": invitation})
    assert result.status_code == 202
    mail = client.app.state.mailer.messages[-1]
    return {"email": email, "request_id": result.json()["request_id"], "code": mail.code}


def age_challenges(client):
    with client.app.state.session_factory.begin() as db:
        db.execute(update(EmailChallenge).values(created_at=utcnow() - timedelta(minutes=2)))


def email_register(client, proof, invitation=None, username="mail_reader"):
    return client.post(EMAIL + "register", headers=BROWSER, json={
        **proof, "username": username, "nickname": "饭搭子", "password": PASSWORD, "invitation": invitation,
    })


def test_invite_registration_email_password_and_code_login_then_reset(mailbox):
    client = mailbox
    client.app.state.settings.registration_mode = "invite"
    with client.app.state.session_factory() as db:
        invitation = create_invitation(db, 1, 1)
    assert email_register(client, ticket(client, invitation=invitation), invitation).status_code == 201
    with client.app.state.session_factory() as db:
        assert db.scalar(select(Invitation.remaining)) == 0
    first = login(client, "cook@example.test")
    assert first.status_code == 200
    age_challenges(client)
    code = ticket(client, purpose="login")
    other = client.post(EMAIL + "login", headers=BROWSER, json=code)
    assert other.status_code == 200
    assert first.json()["user"]["public_id"] == other.json()["user"]["public_id"]
    assert client.post(EMAIL + "login", headers=BROWSER, json=code).status_code == 400
    age_challenges(client)
    recovery = ticket(client, purpose="reset")
    changed = "new-fixture-password"
    assert client.post(EMAIL + "reset", headers=BROWSER, json={**recovery, "password": changed}).status_code == 204
    assert client.get(SECURITY, headers=bearer(first)).status_code == 401
    assert client.get(SECURITY, headers=bearer(other)).status_code == 401
    assert login(client, "mail_reader", PASSWORD).status_code == 401
    assert login(client, "mail_reader", changed).status_code == 200


def test_invite_is_checked_before_sending_without_spending_and_registration_is_atomic(mailbox):
    client = mailbox
    client.app.state.settings.registration_mode = "invite"
    now = utcnow()
    with client.app.state.session_factory() as db:
        valid, expired, revoked, spent = [create_invitation(db, 1, 1) for _ in range(4)]
        for token, values in ((expired, {"expires_at": now - timedelta(seconds=1)}),
                              (revoked, {"revoked_at": now}), (spent, {"remaining": 0})):
            db.execute(update(Invitation).where(Invitation.digest == token_hash(token)).values(**values))
        db.commit()
    for token in (None, "missing-invite", expired, revoked, spent):
        response = client.post(EMAIL + "code", headers=BROWSER,
                               json={"email": "cook@example.test", "purpose": "register", "invitation": token})
        assert response.status_code == 403 and response.json()["error"]["code"] == "invitation_invalid"
    assert not client.app.state.mailer.messages
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(EmailChallenge)) == 0
    tickets = [ticket(client, email, invitation=valid) for email in ("first@example.test", "second@example.test")]
    with client.app.state.session_factory() as db:
        assert db.get(Invitation, token_hash(valid)).remaining == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda entry: email_register(client, entry[1], valid, "cook_" + str(entry[0])).status_code,
                                enumerate(tickets)))
    assert sorted(results) == [201, 409]
    with client.app.state.session_factory() as db:
        assert db.get(Invitation, token_hash(valid)).remaining == 0


@pytest.mark.parametrize("operation", ("modify", "reset", "replace"))
def test_security_mutations_invalidate_prior_email_and_account_challenges(mailbox, operation):
    client = mailbox
    assert email_register(client, ticket(client)).status_code == 201
    auth = bearer(login(client, "mail_reader"))
    age_challenges(client)
    old = ticket(client, purpose="login")
    other_address = "changed@example.test"
    binding = client.post(SECURITY + "/email/code", headers=auth, json={"email": other_address})
    bound = {"email": other_address, "request_id": binding.json()["request_id"],
             "code": client.app.state.mailer.messages[-1].code, "password": PASSWORD}
    new_password = "new-security-fixture-pass"
    if operation == "modify":
        assert client.put(SECURITY + "/password", headers=auth,
                          json={"current_password": PASSWORD, "password": new_password}).status_code == 204
        assert client.put(SECURITY + "/email", headers=auth, json={**bound, "password": new_password}).status_code == 400
    elif operation == "reset":
        age_challenges(client)
        reset = ticket(client, purpose="reset")
        assert client.post(EMAIL + "reset", headers=BROWSER, json={**reset, "password": new_password}).status_code == 204
    else:
        assert client.put(SECURITY + "/email", headers=auth, json=bound).status_code == 204
    assert client.post(EMAIL + "login", headers=BROWSER, json=old).status_code == 400
    with client.app.state.session_factory() as db:
        assert db.get(EmailChallenge, bound["request_id"]).consumed_at is not None


def test_email_binding_challenge_is_bound_to_its_session_and_revocation_during_password_check_wins(mailbox, monkeypatch):
    client = mailbox
    assert email_register(client, ticket(client)).status_code == 201
    first = bearer(login(client, "mail_reader"))
    other = bearer(login(client, "mail_reader"))
    address = "rotated@example.test"
    binding = client.post(SECURITY + "/email/code", headers=first, json={"email": address})
    proof = {"request_id": binding.json()["request_id"], "email": address, "password": PASSWORD,
             "code": client.app.state.mailer.messages[-1].code}
    assert client.put(SECURITY + "/email", headers=other, json=proof).status_code == 400

    from app.models import AuthSession
    passwords = client.app.state.passwords
    original = passwords.verify

    def revoke_during_verification(password, stored):
        verified = original(password, stored)
        with client.app.state.session_factory.begin() as db:
            db.execute(update(AuthSession).values(revoked_at=utcnow()))
        return verified

    monkeypatch.setattr(passwords, "verify", revoke_during_verification)
    assert client.put(SECURITY + "/email", headers=first, json=proof).status_code == 401
    with client.app.state.session_factory() as db:
        assert db.scalar(select(User.email)) == "cook@example.test"


def test_wrong_expired_purpose_and_enumeration_controls(mailbox):
    client = mailbox
    proof = ticket(client, purpose="login")
    assert client.post(EMAIL + "code", headers=BROWSER, json={"email": proof["email"], "purpose": "reset"}).status_code == 429
    assert client.post(EMAIL + "reset", headers=BROWSER, json={**proof, "password": PASSWORD}).status_code == 400
    wrong = "000000" if proof["code"] != "000000" else "000001"
    for _ in range(5):
        assert client.post(EMAIL + "login", headers=BROWSER, json={**proof, "code": wrong}).status_code == 400
    assert client.post(EMAIL + "login", headers=BROWSER, json=proof).status_code == 400
    second = ticket(client, email="fresh@example.test", purpose="reset")
    with client.app.state.session_factory.begin() as db:
        db.execute(update(EmailChallenge).where(EmailChallenge.id == second["request_id"])
                   .values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.post(EMAIL + "reset", headers=BROWSER, json={**second, "password": PASSWORD}).status_code == 400


def test_mail_delivery_failure_and_known_address_do_not_disclose_account_state(mailbox):
    client = mailbox
    assert email_register(client, ticket(client)).status_code == 201
    age_challenges(client)
    known, unknown = (client.post(EMAIL + "code", headers=BROWSER, json={"email": email, "purpose": "reset"})
                      for email in ("cook@example.test", "other@example.test"))
    assert known.status_code == unknown.status_code == 202
    assert {k: v for k, v in known.json().items() if k != "request_id"} == {
        k: v for k, v in unknown.json().items() if k != "request_id"
    }
    assert client.get(SECURITY).status_code == 401

    verification = {}

    def fail(email, purpose, code):
        verification.update(email=email, code=code)
        raise OSError("fixture-smtp-error")

    client.app.state.mailer.send = fail
    rejected = client.post(EMAIL + "code", headers=BROWSER, json={"email": "failed@example.test", "purpose": "reset"})
    assert rejected.status_code == 503 and rejected.json()["error"]["code"] == "email_delivery_failed"
    assert "fixture-smtp-error" not in rejected.text
    with client.app.state.session_factory() as db:
        failed = db.scalar(select(EmailChallenge).where(EmailChallenge.delivered_at.is_(None)))
        assert failed is not None
        verification["request_id"] = failed.id
    assert client.post(EMAIL + "reset", headers=BROWSER,
                       json={**verification, "password": PASSWORD}).status_code == 400


def test_delete_requires_confirmation_clears_media_and_keeps_anonymous_usage(byok):
    app, client = byok
    a = bearer(signed_in(client))
    assert connect(client, a, TEST_A).status_code == 200
    asset = photo(client, a)
    task = new_job(client, a, [asset]).json()["id"]
    assert asyncio.run(scoped(app, {}).process_once())
    url = SECURITY + "/account"
    assert client.request("DELETE", url, headers=a, json={"password": PASSWORD, "confirm_username": "wrong"}).status_code == 403
    assert client.request("DELETE", url, headers=a, json={"password": PASSWORD, "confirm_username": "reader"}).status_code == 204
    assert client.get(API + "/media/" + asset, headers=a).status_code == 401
    assert not list(app.state.settings.media_root.rglob("*.webp"))
    with app.state.session_factory() as db:
        assert db.scalar(select(User.id)) is None
        entry = db.scalar(select(AiUsageLog))
        assert entry.user_id is None and entry.job_id is None and entry.status == "succeeded"
        assert db.get(AiJob, task) is None


def test_account_delete_cancels_queued_work_and_prevents_late_publishing(byok):
    app, client = byok
    auth = bearer(signed_in(client))
    assert connect(client, auth, TEST_A).status_code == 200
    media = photo(client, auth)
    assert new_job(client, auth, [media]).status_code == 202
    runner = scoped(app, {})
    claim = runner.claim()
    assert claim
    settings = app.state.settings
    settings.sticker_enabled, settings.sticker_provider = True, "fake"
    stickers = StickerWorker(settings, app.state.session_factory)
    stickers.heartbeat()
    queued = client.post(API + "/stickers/jobs", headers=auth, json={"media_id": media})
    assert queued.status_code == 202
    sticker_claim = stickers.claim()
    assert sticker_claim
    assert client.request("DELETE", SECURITY + "/account", headers=auth,
                          json={"password": PASSWORD, "confirm_username": "reader"}).status_code == 204
    runner.finish(claim, ProviderError("ai_result_unknown"))
    try:
        stickers.finish(sticker_claim, RenderedSticker((64, 64), (b"fixture",) * 3, 0, 0, 0))
    finally:
        stickers.close()
    assert not list(settings.media_root.rglob("*.webp"))
    with app.state.session_factory() as db:
        assert db.get(AiJob, claim.job_id) is None
        assert db.get(StickerJob, sticker_claim.id) is None
        entry = db.get(AiUsageLog, claim.token)
        assert entry.status == "not_sent" and entry.user_id is None


def test_restore_expires_saved_email_challenges_and_invitation(mailbox, tmp_path):
    client = mailbox
    client.app.state.settings.registration_mode = "invite"
    with client.app.state.session_factory() as db:
        invitation = create_invitation(db, 1, 1)
    proof = ticket(client, invitation=invitation)
    settings = client.app.state.settings
    settings.media_root.mkdir(parents=True, exist_ok=True)
    source, target = tmp_path / "point", tmp_path / "restored"
    maintenance.backup(Path(settings.db_url.database), settings.media_root, source, 0, "phase74-fixture")
    maintenance.restore(source, target, 0)
    with maintenance.readonly(target / "data" / "fooddiary.db") as db:
        assert db.execute("SELECT consumed_at FROM email_challenges WHERE id=?", (proof["request_id"],)).fetchone()[0]
        assert db.execute("SELECT revoked_at FROM account_invitations WHERE digest=?",
                          (token_hash(invitation),)).fetchone()[0]
    config = (target / "ISOLATED.env").read_text()
    assert "EMAIL_MODE=disabled" in config and "AI_BYOK_SIMULATION=false" in config


def test_concurrent_code_use_binds_only_current_account_and_other_sessions_can_be_revoked(mailbox):
    client = mailbox
    registered = email_register(client, ticket(client, email="first@example.test"))
    assert registered.status_code == 201
    first = bearer(login(client, "mail_reader"))
    second = bearer(login(client, "mail_reader"))
    email = "changed@example.test"
    issue = client.post(SECURITY + "/email/code", headers=first, json={"email": email})
    code = client.app.state.mailer.messages[-1].code
    proof = {"email": email, "request_id": issue.json()["request_id"], "code": code, "password": PASSWORD}
    assert client.put(SECURITY + "/email", headers=first, json=proof).status_code == 204
    assert client.get(SECURITY, headers=second).status_code == 401
    assert client.get(SECURITY, headers=first).json()["email"] == email
    assert client.put(SECURITY + "/email", headers=first, json=proof).status_code == 400
    age_challenges(client)
    fresh = ticket(client, email, "login")
    with ThreadPoolExecutor(max_workers=2) as thread:
        results = list(thread.map(lambda _: client.post(EMAIL + "login", headers=BROWSER, json=fresh).status_code, range(2)))
    assert sorted(results) == [200, 400]
    assert client.delete(SECURITY + "/sessions/others", headers=first).status_code == 204
    assert len(client.get(SECURITY, headers=first).json()["sessions"]) == 1
