from alembic import context

from app.core.config import Settings
from app.core.database import Base, build_engine
from app import models  # Import mapped tables before reading metadata.

config = context.config
metadata = Base.metadata


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    url = Settings().db_url
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (connection := config.attributes.get("connection")) is not None:
    run_migrations(connection)
else:
    engine = build_engine(Settings().db_url)
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
