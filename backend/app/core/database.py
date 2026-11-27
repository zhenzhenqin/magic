from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC without an offset and restore it on read, including on SQLite."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("UTC timestamps must carry a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


def build_engine(url: URL):
    options = {"hide_parameters": True, "pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 5}
        if url.database == ":memory:":
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            # The shared catalog groups only the names inside an authorized SQL scope.
            from app.food_names import canonical

            connection.create_function("fooddiary_name", 1, canonical, deterministic=True)
            connection.create_function("fooddiary_catalog_id", 1, lambda name: sha256(name.encode()).hexdigest()[:32],
                                       deterministic=True)
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA journal_mode")
                if url.database != ":memory:" and cursor.fetchone()[0].lower() != "wal":
                    cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

    return engine
