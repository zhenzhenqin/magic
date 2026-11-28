"""Manage account invitations locally on the configured FoodDiary instance."""

import argparse
from getpass import getpass
import sys

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine, utcnow
from app.core.security import token_hash
from app.models.identity import Invitation
from app.services.identity import create_invitation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    create = subcommands.add_parser("create")
    create.add_argument("--uses", type=int, default=1, choices=range(1, 51), metavar="1–50")
    create.add_argument("--hours", type=int, default=48, choices=range(1, 721), metavar="1–720")
    subcommands.add_parser("revoke")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("An interactive terminal is required")
    engine = build_engine(Settings().db_url)
    try:
        with Session(engine) as db:
            if args.action == "create":
                print(create_invitation(db, args.uses, args.hours))
            else:
                digest = token_hash(getpass("Invitation code: ").strip())
                db.execute(update(Invitation).where(Invitation.digest == digest, Invitation.revoked_at.is_(None))
                           .values(revoked_at=utcnow()))
                db.commit()
                print("Invitation revoked if present.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
