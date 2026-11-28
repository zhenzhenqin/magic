from contextlib import asynccontextmanager
import asyncio
import re

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.api.v1 import router
from app.api import ai, catalog, diary, friends, identity, media, stickers
from app.core.config import BACKEND_DIR, Settings
from app.core.database import build_engine
from app.core.exceptions import ApiError, api_error, http_error, problem, unexpected_error, validation_error
from app.core.security import Passwords, RateLimiter
from app.services.storage import LocalStorageProvider
from app.services.ai_credentials import TemporaryCredentials
from app.services.ai_provider import FakeVisionProvider
from app.services.ai_worker import AiWorker
from app.services.email_provider import CaptureEmailProvider, SmtpEmailProvider


async def database_error(_, error: OperationalError):
    code = getattr(error.orig, "sqlite_errorcode", 0)
    if code & 0xff in {5, 6} or (error.orig.args and error.orig.args[0] in (1205, 1213)):
        return problem(503, "database_busy", "数据库正在处理其他操作，请稍后重试。", {"Retry-After": "1"})
    return problem(503, "database_unavailable", "数据库暂时不可用。")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.db_url)
    revision = None
    marker = BACKEND_DIR.parent / "REVISION"
    if settings.app_env == "production" and marker.is_file():
        revision = marker.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Invalid deployed revision")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        worker_task = None
        if settings.ai_byok_simulation and settings.ai_available:
            fake = FakeVisionProvider()
            worker = AiWorker(settings, application.state.session_factory, fake,
                              vault=application.state.ai_credentials, scoped_provider=lambda credential: fake)
            worker_task = asyncio.create_task(worker.run())
        try:
            yield
        finally:
            if worker_task:
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
            application.state.ai_credentials.clear()
            engine.dispose()

    docs = {} if settings.app_env != "production" else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="FoodDiary API", version="0.7.0", debug=False, lifespan=lifespan, **docs)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.passwords = Passwords(settings)
    app.state.rate_limiter = RateLimiter(settings.limit_window_seconds)
    app.state.storage = LocalStorageProvider(settings)
    app.state.ai_credentials = TemporaryCredentials()
    app.state.mailer = None
    if settings.email_mode == "capture":
        app.state.mailer = CaptureEmailProvider()
    elif settings.email_mode == "smtp":
        app.state.mailer = SmtpEmailProvider(settings)

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.app_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
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
        if revision and request.url.path in ("/api/v1/health", "/api/v1/ready"):
            response.headers["X-FoodDiary-Revision"] = revision
        return response

    app.include_router(router, prefix="/api/v1")
    app.include_router(diary.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")
    app.include_router(ai.router, prefix="/api/v1")
    app.include_router(identity.router, prefix="/api/v1")
    app.include_router(stickers.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(friends.router, prefix="/api/v1")
    return app
