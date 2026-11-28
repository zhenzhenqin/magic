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


def add_user(db: Session, data: Registration, password_hash: str, *, email=None) -> User:
    user = User(id=str(uuid4()), public_id="fd_" + uuid4().hex, username=data.username,
                nickname=data.nickname, password_hash=password_hash, email=email,
                email_verified_at=utcnow() if email else None)
    db.add(user)
    db.flush()
    db.add(UserSettings(user_id=user.id))
    return user


def register(db: Session, data: Registration, passwords: Passwords) -> User:
    try:
        user = add_user(db, data, passwords.hash(data.password))
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(User.id).where(User.username == data.username)):
            raise ApiError(409, "username_taken", "该用户名已被使用。") from None
        raise
    return user


def verified_account(db, email):
    return db.scalar(select(User).where(User.email == email, User.email_verified_at.is_not(None), User.is_active.is_(True)))


def login(db: Session, data: Login, settings: Settings, passwords: Passwords, *, device=None):
    user = verified_account(db, data.username) if "@" in data.username else db.scalar(
        select(User).where(User.username == data.username))
    if not passwords.verify(data.password, user.password_hash if user and user.is_active else None):
        raise ApiError(401, "invalid_credentials", "用户名或密码不正确。")
    return new_session(db, user, settings, device=device)


def new_session(db, user, settings, *, device=None):
    token = new_refresh_token()
    now = utcnow()
    session = AuthSession(id=str(uuid4()), user_id=user.id, refresh_token_hash=token_hash(token),
                          expires_at=now + timedelta(seconds=settings.refresh_token_seconds), last_used_at=now, device=device)
    db.add(session)
    db.commit()
    return user, session, token


def cookie_session(db, cookie):
    if cookie:
        return db.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash(cookie)))
    return None


def device_label(request):
    agent = request.headers.get("User-Agent", "")[:500]
    for identifier, label in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                              ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")):
        if identifier in agent:
            return label
    return "浏览器"


def refresh(db: Session, token: str, settings: Settings, identity: tuple[str, str] | None = None):
    now = utcnow()
    incoming = token_hash(token)
    replacement = new_refresh_token()
    new_hash = token_hash(replacement)
    eligible = (AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
    if identity:
        eligible += (AuthSession.user_id == identity[0], AuthSession.id == identity[1])
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
        return True
    matches_cookie = True
    query = update(AuthSession).where(AuthSession.revoked_at.is_(None))
    if identity:
        user_id, session_id = identity
        if token:
            cookie_id = db.scalar(select(AuthSession.id).where(AuthSession.refresh_token_hash == token_hash(token)))
            matches_cookie = cookie_id is None or cookie_id == session_id
        query = query.where(AuthSession.user_id == user_id, AuthSession.id == session_id)
    else:
        query = query.where(AuthSession.refresh_token_hash == token_hash(token))
    db.execute(query.values(revoked_at=utcnow()))
    db.commit()
    return matches_cookie
