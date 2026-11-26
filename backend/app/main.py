from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from app.api.v1 import router
from app.core.config import Settings
from app.core.database import build_engine
from app.core.exceptions import ApiError, api_error, http_error, unexpected_error, validation_error
from app.core.security import Passwords, RateLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.db_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="FoodDiary API", version="0.2.0", debug=False, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.passwords = Passwords(settings)
    app.state.rate_limiter = RateLimiter(settings.limit_window_seconds)

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.app_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "X-FoodDiary-Intent"],
    )
    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(Exception, unexpected_error)

    @app.middleware("http")
    async def prevent_private_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router, prefix="/api/v1")
    return app
