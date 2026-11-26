from pathlib import Path
from secrets import token_urlsafe

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR, Settings
from app.core.database import build_engine


def isolated_settings(path: Path, **overrides):
    path = path.resolve()
    if not path.is_relative_to(Path(BACKEND_DIR).parent) and path.name.endswith("-test.db"):
        overrides.setdefault("media_dir", path.parent / "media")
        overrides.setdefault("ai_enabled", False)
        overrides.setdefault("ai_provider", "qwen")
        return Settings(
            _env_file=None, app_env="test", database_url="sqlite:///" + path.as_posix(),
            jwt_secret=token_urlsafe(48), **overrides,
        )
    raise ValueError("Tests require a test-named database outside the project checkout.")


def migrate(settings: Settings, revision: str = "head"):
    engine = build_engine(settings.db_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    finally:
        engine.dispose()
