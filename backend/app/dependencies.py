from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.exceptions import ApiError, invalid_session
from app.core.security import access_identity
from app.models import AuthSession, User

bearer = HTTPBearer(auto_error=False)


def open_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


Database = Annotated[Session, Depends(open_session)]
Bearer = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def browser_request(
    request: Request,
    intent: Annotated[str | None, Header(alias="X-FoodDiary-Intent", description="浏览器认证 POST 必须传入 browser。")] = None,
) -> None:
    if request.headers.get("origin") not in request.app.state.settings.app_origins:
        raise ApiError(403, "untrusted_origin", "请求来源未获授权。")
    if intent != "browser":
        raise ApiError(403, "csrf_check_failed", "请求缺少浏览器校验标记。")


def current_user(request: Request, db: Database, credentials: Bearer) -> User:
    if not credentials:
        raise invalid_session()
    user_id, session_id = access_identity(request.app.state.settings, credentials.credentials)
    account = db.scalar(
        select(User).join(AuthSession, AuthSession.user_id == User.id)
        .where(User.id == user_id, User.is_active.is_(True), AuthSession.id == session_id,
               AuthSession.revoked_at.is_(None), AuthSession.expires_at > utcnow())
    )
    if not account:
        raise invalid_session()
    return account


CurrentUser = Annotated[User, Depends(current_user)]
