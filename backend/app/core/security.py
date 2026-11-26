from collections import defaultdict, deque
from hashlib import sha256
from secrets import token_urlsafe
from threading import BoundedSemaphore, Lock
from time import monotonic
from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import Settings
from .database import utcnow
from .exceptions import ApiError, invalid_session

ALGORITHM = "HS256"
ISSUER = "fooddiary"
AUDIENCE = "fooddiary-web"
COOKIE_NAME = "fooddiary_refresh"
COOKIE_PATH = "/api/v1/auth"


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return token_urlsafe(32)


def access_token(settings: Settings, user_id: str, session_id: str) -> str:
    now = utcnow()
    return jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": user_id, "sid": session_id,
         "iat": now, "exp": now + timedelta(seconds=settings.access_token_seconds)},
        settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM,
    )


def access_identity(settings: Settings, token: str, *, binding_only: bool = False) -> tuple[str, str]:
    if len(token) > 2048:
        raise invalid_session()
    try:
        data = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[ALGORITHM],
            issuer=ISSUER, audience=AUDIENCE,
            options={"require": ["iss", "aud", "sub", "sid", "iat", "exp"], "verify_exp": not binding_only},
        )
        return str(UUID(data["sub"])), str(UUID(data["sid"]))
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise invalid_session() from None


class Passwords:
    def __init__(self, settings: Settings):
        self.hasher = PasswordHasher(
            memory_cost=settings.argon_memory_kib, time_cost=settings.argon_time_cost,
            parallelism=1, hash_len=32, salt_len=16,
        )
        self.slots = BoundedSemaphore(settings.argon_slots)
        self.dummy = self.hash(token_urlsafe(32))

    def _bounded(self, work, *args):
        if not self.slots.acquire(blocking=False):
            raise ApiError(429, "password_busy", "登录服务繁忙，请稍后重试。", {"Retry-After": "1"})
        try:
            return work(*args)
        finally:
            self.slots.release()

    def hash(self, password: str) -> str:
        return self._bounded(self.hasher.hash, password)

    def verify(self, password: str, stored: str | None) -> bool:
        try:
            self._bounded(self.hasher.verify, stored or self.dummy, password)
            return stored is not None
        except VerifyMismatchError:
            return False


class RateLimiter:
    def __init__(self, window: int, capacity: int = 4096):
        self.window = window
        self.capacity = capacity
        self.next_cleanup = 0.0
        self.events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def check(self, operation: str, address: str, limit: int) -> None:
        now = monotonic()
        with self.lock:
            if now >= self.next_cleanup:
                for key in tuple(self.events):
                    if self.events[key][-1] <= now - self.window:
                        del self.events[key]
                self.next_cleanup = now + self.window
            key = (operation, address)
            if key not in self.events and len(self.events) >= self.capacity:
                raise self._limited(self.window)
            history = self.events[key]
            while history and history[0] <= now - self.window:
                history.popleft()
            if len(history) >= limit:
                raise self._limited(max(1, int(history[0] + self.window - now) + 1))
            history.append(now)

    @staticmethod
    def _limited(seconds: int) -> ApiError:
        return ApiError(429, "rate_limited", "请求过于频繁，请稍后再试。", {"Retry-After": str(seconds)})
