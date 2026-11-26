from datetime import timedelta
from uuid import uuid4

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError, invalid_session
from app.core.security import Passwords, new_refresh_token, token_hash
from app.models import AuthSession, User, UserSettings
from app.schemas import Login, Registration


def register(db: Session, data: Registration, passwords: Passwords) -> User:
    user = User(id=str(uuid4()), public_id="fd_" + uuid4().hex, username=data.username,
                nickname=data.nickname, password_hash=passwords.hash(data.password))
    try:
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(User.id).where(User.username == data.username)):
            raise ApiError(409, "username_taken", "该用户名已被使用。") from None
        raise
    return user


def login(db: Session, data: Login, settings: Settings, passwords: Passwords):
    user = db.scalar(select(User).where(User.username == data.username))
    if not passwords.verify(data.password, user.password_hash if user and user.is_active else None):
        raise ApiError(401, "invalid_credentials", "用户名或密码不正确。")
    token = new_refresh_token()
    now = utcnow()
    session = AuthSession(id=str(uuid4()), user_id=user.id, refresh_token_hash=token_hash(token),
                          expires_at=now + timedelta(seconds=settings.refresh_token_seconds), last_used_at=now)
    db.add(session)
    db.commit()
    return user, session, token


def refresh(db: Session, token: str, settings: Settings):
    now = utcnow()
    incoming = token_hash(token)
    replacement = new_refresh_token()
    new_hash = token_hash(replacement)
    eligible = (AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
    # Update first. This avoids a read-to-write lock upgrade on SQLite and
    # gives concurrent requests exactly one winner via the current digest.
    rotated = db.execute(
        update(AuthSession).where(
            AuthSession.refresh_token_hash == incoming, *eligible,
            exists().where(User.id == AuthSession.user_id, User.is_active.is_(True)),
        ).values(refresh_token_hash=new_hash, previous_token_hash=incoming, last_used_at=now)
    )
    if rotated.rowcount == 1:
        session = db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == new_hash))
        user = db.get(User, session.user_id)
        db.commit()
        return user, session, replacement

    db.rollback()
    previous = db.scalar(select(AuthSession).where(AuthSession.previous_token_hash == incoming, *eligible))
    if previous is not None:
        collision_cutoff = now - timedelta(seconds=settings.refresh_collision_seconds)
        if previous.last_used_at >= collision_cutoff:
            # Leave the winner's cookie and session alone. The browser can retry
            # after the winning response has installed its replacement cookie.
            raise ApiError(409, "refresh_in_progress", "会话正在更新，请稍后重试。")
        db.execute(
            update(AuthSession).where(AuthSession.id == previous.id, AuthSession.previous_token_hash == incoming,
                                      AuthSession.last_used_at < collision_cutoff, *eligible)
            .values(revoked_at=now)
        )
        db.commit()
    raise invalid_session()


def revoke(db: Session, token: str | None, identity: tuple[str, str] | None):
    if identity is None and token is None:
        return
    query = update(AuthSession).where(AuthSession.revoked_at.is_(None))
    if identity:
        user_id, session_id = identity
        query = query.where(AuthSession.user_id == user_id, AuthSession.id == session_id)
    else:
        query = query.where(AuthSession.refresh_token_hash == token_hash(token))
    db.execute(query.values(revoked_at=utcnow()))
    db.commit()
