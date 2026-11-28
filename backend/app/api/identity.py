from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import StringConstraints, field_validator
from sqlalchemy import select, update

from app.api.v1 import RefreshCookie, detach_previous_connection, limit, set_session
from app.core.database import utcnow
from app.core.exceptions import ApiError, invalid_session
from app.core.security import COOKIE_NAME, COOKIE_PATH
from app.dependencies import CurrentUser, Database, browser_request
from app.models import AuthSession, User
from app.models.ai import AiUsageLog
from app.models.diary import MediaAsset
from app.models.stickers import MediaDerivative
from app.schemas import Input, LoginPassword, NewPassword, Registration, UserProfile, normalize_email
from app.services import auth, identity
from app.services.ai_credentials import active_session

router = APIRouter(tags=["邮箱与账号安全"])
browser = [Depends(browser_request)]
Code = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
InvitationCode = Annotated[str, StringConstraints(strip_whitespace=True, max_length=96)]


class EmailInput(Input):
    email: Annotated[str, StringConstraints(max_length=254)]

    _email = field_validator("email")(normalize_email)


class SendEmailCode(EmailInput):
    purpose: Literal["register", "login", "reset"]
    invitation: InvitationCode | None = None


class EmailProof(EmailInput):
    request_id: UUID
    code: Code


class EmailRegistration(Registration, EmailProof):
    invitation: InvitationCode | None = None


class ResetPassword(EmailProof):
    password: NewPassword


class BindEmail(EmailProof):
    password: LoginPassword


class ChangePassword(Input):
    current_password: LoginPassword
    password: NewPassword


class DeleteAccount(Input):
    password: LoginPassword
    confirm_username: Annotated[str, StringConstraints(max_length=32)]


@router.get("/identity/options")
def options(request: Request):
    settings = request.app.state.settings
    return {"email_available": settings.email_mode != "disabled", "registration": settings.registration_policy}


def send(request, db, email, purpose, *, owner=None, invitation=None):
    return identity.issue(db, request.app.state.settings, request.app.state.mailer, email, purpose,
                          request.client.host if request.client else "unknown", owner=owner, invitation=invitation,
                          session_id=request.state.auth_session_id if owner else None)


def consume(request, db, data, purpose, owner=None):
    settings = request.app.state.settings
    limit(request, "email-verify", settings.login_attempts)
    identity.consume(db, settings, data.request_id, data.email, purpose, data.code, owner=owner,
                     session_id=request.state.auth_session_id if owner else None)


@router.post("/auth/email/code", status_code=202, dependencies=browser)
def request_code(data: SendEmailCode, request: Request, db: Database):
    if data.purpose == "register" and request.app.state.settings.registration_policy == "closed":
        raise ApiError(403, "registration_closed", "当前仅限已有账号登录。")
    return send(request, db, data.email, data.purpose, invitation=data.invitation)


@router.post("/auth/email/register", status_code=201, dependencies=browser)
def register(data: EmailRegistration, request: Request, db: Database) -> UserProfile:
    policy = request.app.state.settings.registration_policy
    if policy == "closed":
        raise ApiError(403, "registration_closed", "当前仅限已有账号登录。")
    limit(request, "email-register", request.app.state.settings.register_attempts)
    password_hash = request.app.state.passwords.hash(data.password)
    consume(request, db, data, "register")
    existing = db.scalar(select(User.id).where((User.email == data.email) | (User.username == data.username)))
    if existing or policy == "invite" and not identity.spend_invitation(db, data.invitation):
        db.commit()
        raise ApiError(409, "registration_conflict", "当前无法注册。请检查账号资料和邀请码，重新获取验证码。")
    user = auth.add_user(db, data, password_hash, email=data.email)
    db.commit()
    return UserProfile.model_validate(user)


@router.post("/auth/email/login", dependencies=browser)
def login(data: EmailProof, request: Request, response: Response, db: Database, cookie: RefreshCookie = None):
    consume(request, db, data, "login")
    user = auth.verified_account(db, data.email)
    if user is None:
        db.commit()
        raise identity.invalid_code()
    session = auth.new_session(db, user, request.app.state.settings, device=auth.device_label(request))
    detach_previous_connection(request, db, cookie)
    return set_session(response, request, *session)


def revoke_sessions(db, owner, keep=None):
    conditions = [AuthSession.user_id == owner, AuthSession.revoked_at.is_(None)]
    if keep:
        conditions.append(AuthSession.id != keep)
    db.execute(update(AuthSession).where(*conditions).values(revoked_at=utcnow()))


@router.post("/auth/email/reset", status_code=204, dependencies=browser)
def reset(data: ResetPassword, request: Request, db: Database):
    limit(request, "email-reset", request.app.state.settings.login_attempts)
    password_hash = request.app.state.passwords.hash(data.password)
    consume(request, db, data, "reset")
    user = auth.verified_account(db, data.email)
    if user:
        user.password_hash = password_hash
        revoke_sessions(db, user.id)
        identity.invalidate_challenges(db, request.app.state.settings, user.id, user.email)
        request.app.state.ai_credentials.remove(user.id)
    db.commit()


def verify_password(request, user, password):
    limit(request, "security-password", request.app.state.settings.login_attempts)
    if not request.app.state.passwords.verify(password, user.password_hash):
        raise ApiError(403, "reauthentication_required", "请确认当前账号密码。")


def lock_session(request, db, user):
    identity.begin(db)
    db.refresh(user)
    session_id = request.state.auth_session_id
    if active_session(db, user.id, session_id) is None:
        raise invalid_session()
    return session_id


@router.get("/users/me/security")
def security(request: Request, user: CurrentUser, db: Database):
    current = request.state.auth_session_id
    sessions = db.scalars(select(AuthSession).where(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > utcnow(),
    ).order_by(AuthSession.id != current, AuthSession.last_used_at.desc())).all()
    return {
        "username": user.username, "email": user.email, "email_verified": user.email_verified_at is not None,
        "email_available": request.app.state.mailer is not None,
        "ai_connected": request.app.state.ai_credentials.get(user.id, current) is not None,
        "sessions": [{"id": session.id, "current": session.id == current, "device": session.device or "浏览器",
                      "started_at": session.created_at, "last_used_at": session.last_used_at} for session in sessions],
    }


@router.post("/users/me/security/email/code", status_code=202)
def request_binding(data: EmailInput, request: Request, user: CurrentUser, db: Database):
    return send(request, db, data.email, "bind", owner=user.id)


@router.put("/users/me/security/email", status_code=204)
def bind_email(data: BindEmail, request: Request, user: CurrentUser, db: Database):
    previous_hash, previous_email = user.password_hash, user.email
    verify_password(request, user, data.password)
    consume(request, db, data, "change" if previous_email else "bind", user.id)
    db.refresh(user)
    current = request.state.auth_session_id
    if (user.password_hash != previous_hash or user.email != previous_email
            or active_session(db, user.id, current) is None):
        raise invalid_session()
    if db.scalar(select(User.id).where(User.email == data.email, User.id != user.id)):
        db.commit()
        raise ApiError(409, "email_bind_failed", "无法绑定该邮箱，请检查后重试。")
    user.email, user.email_verified_at = data.email, utcnow()
    identity.invalidate_challenges(db, request.app.state.settings, user.id, previous_email, data.email)
    if previous_email is not None and previous_email != data.email:
        revoke_sessions(db, user.id, keep=current)
        request.app.state.ai_credentials.remove(user.id)
    db.commit()


@router.put("/users/me/security/password", status_code=204)
def change_password(data: ChangePassword, request: Request, user: CurrentUser, db: Database):
    observed = user.password_hash
    verify_password(request, user, data.current_password)
    replacement = request.app.state.passwords.hash(data.password)
    current = lock_session(request, db, user)
    if user.password_hash != observed:
        raise invalid_session()
    user.password_hash = replacement
    revoke_sessions(db, user.id, keep=current)
    identity.invalidate_challenges(db, request.app.state.settings, user.id, user.email)
    request.app.state.ai_credentials.remove(user.id)
    db.commit()


@router.delete("/users/me/security/sessions/others", status_code=204)
def other_sessions(request: Request, user: CurrentUser, db: Database):
    current = lock_session(request, db, user)
    revoke_sessions(db, user.id, keep=current)
    db.commit()


@router.delete("/users/me/security/sessions/{session_id}", status_code=204)
def end_session(session_id: UUID, request: Request, user: CurrentUser, db: Database):
    current = lock_session(request, db, user)
    target = str(session_id)
    if target == current:
        raise ApiError(422, "use_logout", "请使用退出登录结束当前会话。")
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id == target,
                                        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    request.app.state.ai_credentials.remove(user.id, target)
    db.commit()


@router.delete("/users/me/security/account", status_code=204)
def delete_account(data: DeleteAccount, request: Request, user: CurrentUser, db: Database):
    observed = user.password_hash
    verify_password(request, user, data.password)
    lock_session(request, db, user)
    if observed != user.password_hash or data.confirm_username != user.username:
        raise ApiError(403, "account_confirmation", "请核对当前账号及确认内容。")
    media = db.execute(select(MediaAsset.original_key, MediaAsset.thumbnail_key).where(MediaAsset.user_id == user.id))
    variants = db.execute(select(MediaDerivative.storage_key, MediaDerivative.cutout_key, MediaDerivative.thumbnail_key)
                          .where(MediaDerivative.user_id == user.id))
    keys = {key for group in (media, variants) for row in group for key in row if key}
    request.app.state.ai_credentials.remove(user.id)
    identity.invalidate_challenges(db, request.app.state.settings, user.id, user.email)
    db.execute(update(AiUsageLog).where(AiUsageLog.user_id == user.id, AiUsageLog.status == "reserved")
               .values(status="not_sent", error_code="ai_account_deleted"))
    db.delete(user)
    db.commit()
    request.app.state.storage.discard(*keys)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=request.app.state.settings.secure_cookie,
                           httponly=True, samesite="strict")
    return response
