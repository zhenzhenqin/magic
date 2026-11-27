"""Create a closed-beta account locally, using the same validation as registration."""

from getpass import getpass
import sys

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.core.security import Passwords
from app.schemas import Registration
from app.services.auth import register


def main():
    if not sys.stdin.isatty():
        raise SystemExit("An interactive terminal is required")
    settings = Settings()
    username = input("Username: ")
    nickname = input("Nickname: ")
    password = getpass("Password: ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords differ")
    engine = build_engine(settings.db_url)
    try:
        with Session(engine, expire_on_commit=False) as db:
            user = register(db, Registration(username=username, nickname=nickname, password=password), Passwords(settings))
            print(f"Account created. Public ID: {user.public_id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
