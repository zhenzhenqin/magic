from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR.parent / ".env", env_file_encoding="utf-8-sig", env_ignore_empty=True,
        hide_input_in_errors=True, extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///data/fooddiary.db"
    app_origins: list[str] = ["http://127.0.0.1:5173"]
    jwt_secret: SecretStr
    access_token_seconds: int = Field(default=900, ge=1, le=3600)
    refresh_token_seconds: int = Field(default=2_592_000, ge=5, le=7_776_000)
    refresh_collision_seconds: int = Field(default=10, ge=1, le=30)
    login_attempts: int = Field(default=10, ge=1, le=1000)
    register_attempts: int = Field(default=8, ge=1, le=1000)
    refresh_attempts: int = Field(default=60, ge=1, le=1000)
    limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    argon_memory_kib: int = Field(default=32768, ge=19456, le=131072)
    argon_time_cost: int = Field(default=2, ge=2, le=5)
    argon_slots: int = Field(default=2, ge=1, le=4)

    @field_validator("app_origins")
    @classmethod
    def valid_origins(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("Provide at least one trusted browser origin")
        for value in values:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or any(
                (parsed.path, parsed.query, parsed.fragment, "*" in value)
            ):
                raise ValueError("Browser origins must be explicit HTTP(S) origins without paths")
        return values

    @model_validator(mode="after")
    def secure_configuration(self):
        key = self.jwt_secret.get_secret_value()
        if len(key.encode()) < 32 or len(set(key)) < 12 or key.lower().startswith(("example", "change-me", "replace-me")):
            raise ValueError("JWT_SECRET must be a high-entropy value of at least 32 bytes")
        if self.app_env == "production" and any(not origin.startswith("https://") for origin in self.app_origins):
            raise ValueError("Production browser origins require HTTPS")
        return self

    @property
    def secure_cookie(self) -> bool:
        return self.app_env == "production"

    @property
    def db_url(self):
        url = make_url(self.database_url)
        if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
            file = Path(url.database)
            if not file.is_absolute():
                url = url.set(database=(BACKEND_DIR / file).resolve().as_posix())
        return url
