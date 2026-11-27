from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
AiProvider = Literal["qwen", "deepseek", "fake"]
REAL_AI_PROVIDERS = ("qwen", "deepseek")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com"
DEEPSEEK_VISION_MODEL = "deepseek-flash"
DEEPSEEK_COMPACT_BODY_BYTES = 65_536
DEEPSEEK_COMPACT_OUTPUT_TOKENS = 1_024
QWEN_REGIONS = "cn-beijing|ap-southeast-1|cn-hongkong|us-east-1|ap-northeast-1|eu-central-1"
QWEN_ENDPOINT = re.compile(
    r"https://(?:dashscope(?:-intl)?\.aliyuncs\.com|cn-hongkong\.dashscope\.aliyuncs\.com|"
    rf"(?!trial\.)[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.(?:{QWEN_REGIONS})\.maas\.aliyuncs\.com)"
    r"/compatible-mode/v1/?", re.ASCII,
)


def validate_qwen_base_url(value: str) -> str:
    if value and not QWEN_ENDPOINT.fullmatch(value):
        raise ValueError("Provide a documented HTTPS Model Studio regional or workspace endpoint")
    return value.rstrip("/")


def validate_ai_base_url(provider: AiProvider, value: str) -> str:
    if provider == "deepseek":
        if value not in ("", DEEPSEEK_ENDPOINT, DEEPSEEK_ENDPOINT + "/"):
            raise ValueError("DeepSeek requires the official HTTPS API origin")
        return value.rstrip("/")
    return validate_qwen_base_url(value)


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
    media_dir: Path = Path("data/media")
    image_upload_bytes: int = Field(default=10_485_760, ge=1024, le=20_971_520)
    image_max_pixels: int = Field(default=20_000_000, ge=100, le=25_000_000)
    image_max_edge: int = Field(default=1600, ge=64, le=2048)
    image_thumbnail_edge: int = Field(default=400, ge=32, le=800)
    image_process_slots: int = Field(default=1, ge=1, le=2)
    media_upload_attempts: int = Field(default=30, ge=1, le=500)
    media_user_bytes: int = Field(default=209_715_200, ge=1)
    media_user_files: int = Field(default=1000, ge=1)
    media_orphan_seconds: int = Field(default=86_400, ge=60)
    sticker_enabled: bool = False
    sticker_provider: Literal["onnx", "fake"] = "onnx"
    sticker_model_dir: Path = Path("data/models/rembg")
    sticker_edge: int = Field(default=768, ge=256, le=1024)
    sticker_threads: int = Field(default=1, ge=1, le=2)
    sticker_timeout_seconds: int = Field(default=25, ge=1, le=120)
    sticker_min_free_bytes: int = Field(default=536_870_912, ge=0)
    sticker_pending_per_user: int = Field(default=12, ge=1, le=40)
    ai_enabled: bool = False
    ai_provider: AiProvider = "qwen"
    ai_base_url: str = ""
    ai_api_key: SecretStr | None = None
    ai_model: str = Field(default="", max_length=100)
    ai_timeout_seconds: int = Field(default=40, ge=1, le=120)
    ai_max_output_tokens: int = Field(default=3000, ge=256, le=8192)
    ai_max_images: int = Field(default=3, ge=1, le=5)
    ai_image_edge: int = Field(default=1024, ge=256, le=1280)
    ai_max_concurrent_jobs: int = Field(default=1, ge=1, le=4)
    ai_user_daily_limit: int = Field(default=10, ge=1, le=1000)
    ai_global_daily_limit: int = Field(default=30, ge=1, le=10000)
    ai_qwen_cumulative_limit: int = Field(default=0, ge=0, le=1_000_000)
    ai_deepseek_cumulative_limit: int = Field(default=0, ge=0, le=1_000_000)
    ai_deepseek_compact_request: bool = False
    ai_max_attempts: int = Field(default=3, ge=1, le=5)
    ai_job_retention_seconds: int = Field(default=604_800, ge=86_400, le=2_592_000)
    ai_usage_retention_seconds: int = Field(default=2_592_000, ge=86_400, le=7_776_000)
    ai_job_ttl_seconds: int = Field(default=900, ge=180, le=3600)

    @field_validator("ai_base_url")
    @classmethod
    def valid_ai_url(cls, value: str, info: ValidationInfo) -> str:
        return validate_ai_base_url(info.data.get("ai_provider", "qwen"), value)

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
        if self.app_env == "production" and self.ai_provider == "fake":
            raise ValueError("Production prohibits the fake AI provider")
        if self.app_env == "production" and self.sticker_provider == "fake":
            raise ValueError("Production prohibits the fake sticker provider")
        if self.ai_provider == "deepseek" and self.ai_model not in ("", DEEPSEEK_VISION_MODEL):
            raise ValueError("DeepSeek food recognition requires deepseek-flash")
        if self.ai_deepseek_compact_request and (self.ai_provider != "deepseek" or self.ai_max_images != 1
                                                or self.ai_max_output_tokens > DEEPSEEK_COMPACT_OUTPUT_TOKENS):
            raise ValueError("Compact DeepSeek requests require one image and at most 1024 output tokens")
        if (self.ai_enabled or self.sticker_enabled) and (
            self.db_url.get_backend_name() != "sqlite" or self.db_url.database in (None, "", ":memory:")
        ):
            raise ValueError("Image jobs require a shared SQLite file")
        return self

    @property
    def ai_available(self) -> bool:
        return self.ai_enabled and (self.ai_provider == "fake" or bool(
            self.ai_base_url and self.ai_model and self.ai_api_key and self.ai_api_key.get_secret_value().strip()
        ))

    @property
    def ai_model_name(self) -> str:
        return self.ai_model or ("local-fixture" if self.ai_provider == "fake" else "")

    @property
    def ai_cumulative_limit(self) -> int:
        limits = {"qwen": self.ai_qwen_cumulative_limit, "deepseek": self.ai_deepseek_cumulative_limit}
        return limits.get(self.ai_provider, 0)

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

    @property
    def media_root(self) -> Path:
        return (BACKEND_DIR / self.media_dir).resolve()
