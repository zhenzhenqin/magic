import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import build_engine
from app.services.ai_provider import build_provider
from app.services.ai_worker import AiWorker


def main():
    settings = Settings()
    if not settings.ai_available or settings.ai_byok_simulation:
        print("FoodDiary AI is disabled or not configured.")
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    engine = build_engine(settings.db_url)
    try:
        logging.info("FoodDiary AI worker started")
        asyncio.run(AiWorker(settings, sessionmaker(bind=engine, expire_on_commit=False), build_provider(settings)).run())
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
