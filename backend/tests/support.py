from pathlib import Path
from secrets import token_urlsafe
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table

from app.core.config import BACKEND_DIR, Settings
from app.core.database import build_engine, utcnow
from app.core.security import Passwords, access_token, token_hash
from app.services.storage import LocalStorageProvider


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


def legacy_account(db, settings, *, timezone="Asia/Tokyo"):
    """Seed old schemas with their own columns, then exercise current HTTP routes after upgrading."""
    from tests.test_identity import PASSWORD

    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=db.connection())
              for name in ("users", "user_settings", "auth_sessions")}
    now = utcnow().replace(tzinfo=None)
    owner, session = str(uuid4()), str(uuid4())
    cookie = token_urlsafe(32)
    db.execute(tables["users"].insert().values(
        id=owner, public_id="fd_" + uuid4().hex, username="reader", nickname="手账读者",
        password_hash=Passwords(settings).hash(PASSWORD), is_active=True, created_at=now, updated_at=now,
    ))
    db.execute(tables["user_settings"].insert().values(
        user_id=owner, timezone=timezone, show_calories=True, show_nutrition=True, created_at=now, updated_at=now,
    ))
    db.execute(tables["auth_sessions"].insert().values(
        id=session, user_id=owner, refresh_token_hash=token_hash(cookie), created_at=now, last_used_at=now,
        expires_at=now + timedelta(days=1),
    ))
    return owner, {"Authorization": "Bearer " + access_token(settings, owner, session)}, cookie


def legacy_photo(db, settings, owner):
    from tests.test_diary import image_bytes

    identifier = uuid4()
    keys = (f"originals/{identifier.hex}.webp", f"thumbnails/{identifier.hex}.webp")
    storage = LocalStorageProvider(settings)
    original, thumbnail = map(storage.path, keys)
    for path in (original, thumbnail):
        path.parent.mkdir(parents=True, exist_ok=True)
    width, height = storage._encode(BytesIO(image_bytes()), original, thumbnail)
    payload = original.read_bytes()
    now = utcnow().replace(tzinfo=None)
    table = Table("media_assets", MetaData(), autoload_with=db.connection())
    db.execute(table.insert().values(
        id=str(identifier), user_id=owner, original_key=keys[0], thumbnail_key=keys[1], content_type="image/webp",
        size_bytes=len(payload), thumbnail_size_bytes=thumbnail.stat().st_size, width=width, height=height,
        sha256=sha256(payload).hexdigest(), status="draft", created_at=now, updated_at=now,
    ))
    return str(identifier), payload
