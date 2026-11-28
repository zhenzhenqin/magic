"""Offline deployment, backup and isolated recovery for the FoodDiary SQLite store."""

import argparse
from contextlib import closing
from datetime import UTC, datetime
from hashlib import file_digest
import json
from pathlib import Path
import re
from shutil import copyfile, disk_usage, rmtree
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR, Settings
from app.core.database import build_engine
from app.services.storage import FILE_KEY
from app.services.ai_control import processing_identity

MANIFEST = "manifest.json"
DATABASE = "fooddiary.db"
SCHEMA = 1
DAILY = re.compile(r"daily-[0-9]{8}T[0-9]{6}-[0-9]+")


def private_file(path):
    if not path.is_file() or path.is_symlink() or path.resolve() != path:
        raise ValueError("Backup or media file is missing or linked")
    return path


def readonly(path):
    return sqlite3.connect(private_file(path).as_uri() + "?mode=ro", uri=True, timeout=5)


def check_sqlite(db):
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("SQLite integrity or foreign key validation failed")


def media_keys(db):
    keys = set()
    for row in db.execute("SELECT original_key,thumbnail_key FROM media_assets"):
        keys.update(row)
    for row in db.execute("SELECT storage_key,cutout_key,thumbnail_key FROM media_derivatives"):
        keys.update(row)
    if any(not isinstance(key, str) or not FILE_KEY.fullmatch(key) or key.startswith("staging/") for key in keys):
        raise ValueError("Database refers to an invalid media key")
    return keys


def describe(path):
    with private_file(path).open("rb") as stream:
        return {"bytes": path.stat().st_size, "sha256": file_digest(stream, "sha256").hexdigest()}


def new_tree(target, build):
    if target.exists() or target.is_symlink():
        raise FileExistsError("Destination already exists")
    stage = Path(tempfile.mkdtemp(prefix=".fooddiary-", dir=target.parent)).resolve()
    try:
        build(stage)
        # A private O_EXCL marker serializes publication, including an empty destination.
        marker = target.with_name(target.name + ".lock")
        with marker.open("x"):
            pass
        try:
            if target.exists() or target.is_symlink():
                raise FileExistsError("Destination already exists")
            stage.rename(target)
        finally:
            marker.unlink()
    finally:
        if stage.exists():
            rmtree(stage)


def need_space(parent, count, reserve):
    if reserve < 0 or disk_usage(parent).free < count + reserve:
        raise ValueError("Insufficient disk space for a complete recovery point and reserved headroom")


def clone_database(source, destination):
    with closing(readonly(source)) as db, closing(sqlite3.connect(destination)) as copy:
        db.backup(copy)
        check_sqlite(copy)
        copy.execute("PRAGMA journal_mode=DELETE")
    destination.chmod(0o600)


def seal_database(path):
    with closing(sqlite3.connect(private_file(path))) as db:
        busy, *_ = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if busy or db.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
            raise ValueError("Could not checkpoint an open database")
        check_sqlite(db)


def migrate_candidate(path):
    path = private_file(path)
    if not path.name.startswith(".candidate-"):
        raise ValueError("Migration can only run on an isolated candidate")
    settings = Settings(database_url="sqlite:///" + path.as_posix())
    engine = build_engine(settings.db_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
    finally:
        engine.dispose()
    seal_database(path)


def put_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    copyfile(private_file(source), destination)
    destination.chmod(0o600)


def backup(database, media, target, reserve, revision):
    if not media.is_dir() or media.resolve() != media or target.is_relative_to(media):
        raise ValueError("Backup needs a private media source and separate destination")

    def build(stage):
        # Management stops all writers first. A transaction also excludes accidental DB writes
        # while another connection takes the WAL-aware snapshot and its media is copied.
        with closing(sqlite3.connect(private_file(database), timeout=5)) as guard:
            guard.execute("BEGIN IMMEDIATE")
            keys = media_keys(guard)
            size = sum(private_file(media / key).stat().st_size for key in keys)
            allocated = guard.execute("PRAGMA page_count").fetchone()[0] * guard.execute("PRAGMA page_size").fetchone()[0]
            need_space(stage, size + allocated, reserve)
            file = stage / DATABASE
            clone_database(database, file)
            index = {}
            for key in sorted(keys):
                path = stage / "media" / key
                put_file(media / key, path)
                index[key] = describe(path)
            (stage / "media").mkdir(exist_ok=True)
            manifest = {
                "format": SCHEMA,
                "created_at": datetime.now(UTC).isoformat(),
                "release": revision,
                "database": describe(file),
                "media": index,
            }
            (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (stage / MANIFEST).chmod(0o600)
            verify(stage)

    new_tree(target, build)


def verify(root):
    manifest = json.loads(private_file(root / MANIFEST).read_text(encoding="utf-8"))
    if manifest["format"] != SCHEMA or describe(root / DATABASE) != manifest["database"]:
        raise ValueError("Database checksum or backup format is invalid")
    with closing(readonly(root / DATABASE)) as db:
        check_sqlite(db)
        keys = media_keys(db)
        if set(manifest["media"]) != keys:
            raise ValueError("Media manifest does not match database references")
    for key in keys:
        if describe(root / "media" / key) != manifest["media"][key]:
            raise ValueError("A media checksum does not match the recovery point")
    return manifest


def restore(root, target, reserve):
    manifest = verify(root)
    size = manifest["database"]["bytes"] + sum(item["bytes"] for item in manifest["media"].values())
    need_space(target.parent, size + manifest["database"]["bytes"], reserve)

    def build(stage):
        database = stage / "data" / DATABASE
        put_file(root / DATABASE, database)
        if describe(database) != manifest["database"]:
            raise ValueError("Database changed during restore")
        for key, expected in manifest["media"].items():
            path = stage / "media" / key
            put_file(root / "media" / key, path)
            if describe(path) != expected:
                raise ValueError("Media changed during restore")
        (stage / "media").mkdir(exist_ok=True)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            now = datetime.now(UTC).replace(tzinfo=None).isoformat(" ")
            db.execute("UPDATE auth_sessions SET revoked_at=? WHERE revoked_at IS NULL", (now,))
            db.execute("""UPDATE share_permissions SET flags=0, history_start=NULL, history_scope='today',
                       granted_at=NULL, version=version+1, updated_at=? WHERE flags<>0""", (now,))
            db.execute("""UPDATE ai_jobs SET status='cancelled', claim_token=NULL, lease_until=NULL,
                       error_code='restored_job_cancelled', completed_at=?, updated_at=?
                       WHERE status IN ('pending','running')""", (now, now))
            db.execute("DELETE FROM ai_worker_heartbeats")
            db.execute("DELETE FROM sticker_runtime")
            db.execute("DELETE FROM media_write_reservations")
            check_sqlite(db)
        settings = stage / "ISOLATED.env"
        settings.write_text(
            f'DATABASE_URL="sqlite:///{(target / "data" / DATABASE).as_posix()}"\n'
            f'MEDIA_DIR="{(target / "media").as_posix()}"\n'
            "PUBLIC_REGISTRATION=false\nSTICKER_ENABLED=false\nAI_ENABLED=false\n"
            "AI_DEEPSEEK_CUMULATIVE_LIMIT=0\nAI_QWEN_CUMULATIVE_LIMIT=0\n", encoding="utf-8",
        )
        settings.chmod(0o600)

    new_tree(target, build)


def retain_daily(root, newest):
    if not DAILY.fullmatch(newest.name) or newest.parent != root or root.resolve() != root:
        raise ValueError("Retention requires a daily point in the explicit backup root")
    points = sorted((p for p in root.iterdir() if DAILY.fullmatch(p.name)
                     and p.is_dir() and not p.is_symlink()), reverse=True)
    if not points or not newest.is_dir() or newest != points[0]:
        raise ValueError("Retention requires the latest daily recovery point")
    verify(newest)
    for point in points[3:]:
        marker = point / MANIFEST
        if marker.is_file() and not marker.is_symlink():
            data = json.loads(private_file(marker).read_text(encoding="utf-8"))
            if data.get("format") == SCHEMA and {"database", "media", "created_at"} <= data.keys():
                rmtree(point)
                print(f"Removed expired FoodDiary daily point {point.name}")


def worker_ready(unit, since):
    settings = Settings()
    # Parse nanoseconds from GNU date, matching the precision of stored UTC times.
    start = datetime.fromisoformat(since).astimezone(UTC).replace(tzinfo=None).isoformat(" ")
    with closing(readonly(Path(settings.db_url.database).resolve())) as db:
        if unit == "fooddiary-sticker.service" and settings.sticker_enabled:
            return db.execute("SELECT 1 FROM sticker_runtime WHERE id=1 AND heartbeat>=?", (start,)).fetchone() is not None
        if unit == "fooddiary-ai.service" and settings.ai_available:
            return db.execute("SELECT 1 FROM ai_worker_heartbeats WHERE configuration=? AND checked_at>=?",
                              (processing_identity(settings), start)).fetchone() is not None
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reserve-bytes", type=int, default=2 * 1024**3)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup")
    create.add_argument("database", type=Path)
    create.add_argument("media", type=Path)
    create.add_argument("target", type=Path)
    create.add_argument("--release", required=True)
    review = commands.add_parser("verify")
    review.add_argument("source", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("source", type=Path)
    recover.add_argument("target", type=Path)
    check = commands.add_parser("check-db")
    check.add_argument("source", type=Path)
    seal = commands.add_parser("seal-db", help="checkpoint an offline SQLite file before an atomic rename")
    seal.add_argument("source", type=Path)
    migrate = commands.add_parser("migrate-candidate", help="upgrade an isolated copy before activation")
    migrate.add_argument("source", type=Path)
    retain = commands.add_parser("retain-daily")
    retain.add_argument("root", type=Path)
    retain.add_argument("newest", type=Path)
    worker = commands.add_parser("worker-ready")
    worker.add_argument("unit", choices=("fooddiary-sticker.service", "fooddiary-ai.service"))
    worker.add_argument("since")
    args = parser.parse_args()
    if args.command == "backup":
        backup(args.database.absolute(), args.media.absolute(), args.target.absolute(), args.reserve_bytes, args.release)
    elif args.command == "verify":
        manifest = verify(args.source.absolute())
        print(f"Verified database and {len(manifest['media'])} media files")
    elif args.command == "restore":
        restore(args.source.absolute(), args.target.absolute(), args.reserve_bytes)
        print("Isolated copy created with sessions revoked, grants off and real AI disabled")
    elif args.command == "seal-db":
        seal_database(args.source.absolute())
    elif args.command == "migrate-candidate":
        migrate_candidate(args.source.absolute())
    elif args.command == "retain-daily":
        retain_daily(args.root.absolute(), args.newest.absolute())
    elif args.command == "worker-ready":
        if not worker_ready(args.unit, args.since):
            parser.exit(1)
    else:
        with closing(readonly(args.source.absolute())) as db:
            check_sqlite(db)
        print("SQLite integrity and foreign keys verified")


if __name__ == "__main__":
    main()
