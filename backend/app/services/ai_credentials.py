from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import select

from app.core.database import utcnow
from app.models import AuthSession, User


@dataclass(frozen=True)
class Credential:
    ref: str
    owner: str
    session_id: str
    expires_at: datetime
    key: SecretStr = field(repr=False)


class TemporaryCredentials:
    """One active credential per account, bound to the browser session that connected it."""

    def __init__(self):
        self._entries: dict[str, Credential] = {}
        self._lock = Lock()

    def connect(self, owner, session_id, key, ttl, session_expiry):
        now = utcnow()
        connected = Credential(str(uuid4()), owner, session_id, min(session_expiry, now + timedelta(seconds=ttl)), key)
        with self._lock:
            self._prune(now)
            self._entries[owner] = connected
        return connected

    def _prune(self, now):
        for owner in [owner for owner, entry in self._entries.items() if entry.expires_at <= now]:
            del self._entries[owner]

    def get(self, owner, session_id, ref=None):
        with self._lock:
            self._prune(utcnow())
            entry = self._entries.get(owner)
            if entry and entry.session_id == session_id and (ref is None or entry.ref == ref):
                return entry
        return None

    def remove(self, owner, session_id=None):
        with self._lock:
            entry = self._entries.get(owner)
            if entry and (session_id is None or entry.session_id == session_id):
                del self._entries[owner]

    def sweep(self, db):
        with self._lock:
            self._prune(utcnow())
            entries = tuple(self._entries.values())
        for entry in entries:
            if active_session(db, entry.owner, entry.session_id) is None:
                with self._lock:
                    if self._entries.get(entry.owner) is entry:
                        del self._entries[entry.owner]

    def clear(self):
        with self._lock:
            self._entries.clear()


def active_session(db, owner, session_id):
    return db.scalar(select(AuthSession).join(User, User.id == AuthSession.user_id).where(
        AuthSession.id == session_id, AuthSession.user_id == owner, AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > utcnow(), User.is_active.is_(True),
    ))


def job_credential(db, vault, job):
    if vault is None or not job.credential_ref or not job.credential_session_id:
        return None
    if active_session(db, job.user_id, job.credential_session_id) is None:
        return None
    return vault.get(job.user_id, job.credential_session_id, job.credential_ref)
