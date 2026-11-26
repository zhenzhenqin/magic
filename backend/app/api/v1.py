from math import ceil
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import utcnow
from app.core.exceptions import ApiError, ProblemResponse, invalid_session
from app.core.security import COOKIE_NAME, COOKIE_PATH, access_identity, access_token
from app.dependencies import Bearer, CurrentUser, Database, browser_request
from app.models import AuthSession, User, UserSettings
from app.schemas import AuthResponse, Login, ProfilePatch, Registration, SettingsPatch, SystemStatus, UserPreferences, UserProfile
from app.services import auth

router = APIRouter(responses={
    422: {"model": ProblemResponse, "description": "输入字段校验失败"},
    500: {"model": ProblemResponse, "description": "服务内部错误"},
})
authentication = APIRouter(prefix="/auth", tags=["认证"], dependencies=[Depends(browser_request)],
                           responses={403: {"model": ProblemResponse}, 429: {"model": ProblemResponse}})
users = APIRouter(prefix="/users/me", tags=["个人中心"], responses={401: {"model": ProblemResponse}})
RefreshCookie = Annotated[str | None, Cookie(alias=COOKIE_NAME, max_length=128)]


def limit(request: Request, operation: str, count: int):
    address = request.client.host if request.client else "unknown"
    request.app.state.rate_limiter.check(operation, address, count)


def set_session(response: Response, request: Request, user: User, session: AuthSession, token: str) -> AuthResponse:
    settings = request.app.state.settings
    remaining = (session.expires_at - utcnow()).total_seconds()
    response.set_cookie(
        COOKIE_NAME, token, max_age=max(0, ceil(remaining)), expires=session.expires_at,
        httponly=True, secure=settings.secure_cookie, samesite="strict", path=COOKIE_PATH,
    )
    return AuthResponse(access_token=access_token(settings, user.id, session.id),
                        expires_in=settings.access_token_seconds, user=UserProfile.model_validate(user))


@router.get("/health", tags=["系统"])
def health() -> SystemStatus:
    """检查应用进程是否运行。"""
    return SystemStatus(status="ok")


@router.get("/ready", tags=["系统"], responses={503: {"model": ProblemResponse}})
def ready(db: Database) -> SystemStatus:
    """检查数据库连接与本阶段业务表。"""
    try:
        db.execute(text("SELECT 1"))
        for model in (User, UserSettings, AuthSession):
            db.execute(select(model.__table__).limit(0))
    except SQLAlchemyError:
        raise ApiError(503, "database_unavailable", "数据库暂时不可用。") from None
    return SystemStatus(status="ready")


@authentication.post("/register", status_code=201, responses={409: {"model": ProblemResponse}})
def register(data: Registration, request: Request, db: Database) -> UserProfile:
    """创建用户名、密码和昵称，成功后由客户端引导登录。"""
    limit(request, "register", request.app.state.settings.register_attempts)
    user = auth.register(db, data, request.app.state.passwords)
    return UserProfile.model_validate(user)


@authentication.post("/login", responses={401: {"model": ProblemResponse}})
def login(data: Login, request: Request, response: Response, db: Database) -> AuthResponse:
    """校验口令，返回访问令牌并设置 HttpOnly 刷新 Cookie。"""
    settings = request.app.state.settings
    limit(request, "login", settings.login_attempts)
    return set_session(response, request, *auth.login(db, data, settings, request.app.state.passwords))


@authentication.post("/refresh", responses={401: {"model": ProblemResponse}, 409: {"model": ProblemResponse}})
def refresh(request: Request, response: Response, db: Database, cookie: RefreshCookie = None) -> AuthResponse:
    """轮换刷新 Cookie 并返回新的短期访问令牌。"""
    settings = request.app.state.settings
    limit(request, "refresh", settings.refresh_attempts)
    if not cookie:
        raise invalid_session()
    return set_session(response, request, *auth.refresh(db, cookie, settings))


@authentication.post("/logout", status_code=204)
def logout(request: Request, db: Database, credentials: Bearer, cookie: RefreshCookie = None) -> Response:
    """撤销当前会话并清除刷新 Cookie。"""
    settings = request.app.state.settings
    identity = None
    if credentials:
        try:
            identity = access_identity(settings, credentials.credentials)
        except ApiError:
            pass
    auth.revoke(db, cookie, identity)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=settings.secure_cookie, httponly=True, samesite="strict")
    return response


@users.get("")
def profile(user: CurrentUser) -> UserProfile:
    return UserProfile.model_validate(user)


@users.patch("")
def update_profile(data: ProfilePatch, user: CurrentUser, db: Database) -> UserProfile:
    user.nickname = data.nickname
    db.commit()
    return UserProfile.model_validate(user)


@users.get("/settings")
def preferences(user: CurrentUser, db: Database) -> UserPreferences:
    return UserPreferences.model_validate(db.get(UserSettings, user.id))


@users.patch("/settings")
def update_preferences(data: SettingsPatch, user: CurrentUser, db: Database) -> UserPreferences:
    preferences = db.get(UserSettings, user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(preferences, field, value)
    db.commit()
    return UserPreferences.model_validate(preferences)


router.include_router(authentication)
router.include_router(users)
