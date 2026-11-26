import argparse
import json

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.services.storage import LocalStorageProvider


def main():
    parser = argparse.ArgumentParser(description="Inspect or clean expired unreferenced FoodDiary media.")
    parser.add_argument("--apply", action="store_true", help="Apply the cleanup. The default is dry-run.")
    args = parser.parse_args()
    settings = Settings()
    engine = build_engine(settings.db_url)
    try:
        with Session(engine) as db:
            result = LocalStorageProvider(settings).sweep(db, apply=args.apply)
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", **result}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
