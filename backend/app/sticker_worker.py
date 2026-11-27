import time

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import build_engine
from app.services.sticker_worker import StickerWorker


def main():
    settings = Settings()
    if not settings.sticker_enabled:
        raise SystemExit("Sticker Worker is disabled; set STICKER_ENABLED=true")
    engine = build_engine(settings.db_url)
    worker = StickerWorker(settings, sessionmaker(engine, expire_on_commit=False))
    try:
        while True:
            if not worker.run_once():
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()
        engine.dispose()


if __name__ == "__main__":
    main()
