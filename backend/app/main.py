from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.api.v1 import router
from app.api import diary, media
from app.core.config import Settings
from app.core.database import build_engine
from app.core.exceptions import ApiError, api_error, http_error, problem, unexpected_error, validation_error
from app.core.security import Passwords, RateLimiter
from app.services.storage import LocalStorageProvider


async def database_error(_, error: OperationalError):
    code = getattr(error.orig, "sqlite_errorcode", 0)
    if code & 0xff in {5, 6} or (error.orig.args and error.orig.args[0] in (1205, 1213)):
        return problem(503, "database_busy", "数据库正在处理其他操作，请稍后重试。", {"Retry-After": "1"})
    return problem(503, "database_unavailable", "数据库暂时不可用。")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.db_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="FoodDiary API", version="0.3.0", debug=False, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.passwords = Passwords(settings)
    app.state.rate_limiter = RateLimiter(settings.limit_window_seconds)
    app.state.storage = LocalStorageProvider(settings)

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.app_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-FoodDiary-Intent", "Idempotency-Key"],
    )
    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(OperationalError, database_error)
    app.add_exception_handler(Exception, unexpected_error)

    @app.middleware("http")
    async def prevent_private_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router, prefix="/api/v1")
    app.include_router(diary.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")
    return app
