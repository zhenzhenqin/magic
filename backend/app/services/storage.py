import os
import re
from datetime import timedelta
from hashlib import file_digest
from pathlib import Path
from threading import BoundedSemaphore
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models import User
from app.models.ai import AiJob, AiJobMedia
from app.models.diary import MealMedia, MediaAsset

FILE_KEY = re.compile(r"(originals|thumbnails|staging)/[0-9a-f]{32}(?:-(?:original|thumbnail))?\.webp")
SUPPORTED = ("JPEG", "PNG", "WEBP")
MEDIA_MISSING = "图片不存在或不可访问。"


def lock_owner(db: Session, owner: str):
    table = User.__table__
    db.execute(update(table).where(table.c.id == owner).values(updated_at=table.c.updated_at))


def owned_media(db: Session, owner: str, media_id: str):
    asset = db.scalar(select(MediaAsset).where(MediaAsset.id == media_id, MediaAsset.user_id == owner))
    if not asset:
        raise ApiError(404, "media_not_found", MEDIA_MISSING)
    return asset


def referenced(media_id):
    return exists().where(MealMedia.media_id == media_id)


def used_by_ai(media_id, now):
    return exists().where(
        AiJobMedia.media_id == media_id, AiJobMedia.job_id == AiJob.id, AiJobMedia.user_id == AiJob.user_id,
        ((AiJob.status == "pending") & (AiJob.expires_at > now))
        | ((AiJob.status == "running") & ((AiJob.lease_until > now) | (AiJob.expires_at > now))),
    )


class LocalStorageProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.media_root
        self.slots = BoundedSemaphore(settings.image_process_slots)

    def path(self, key: str) -> Path:
        if not FILE_KEY.fullmatch(key):
            raise ValueError("Invalid storage key")
        target = self.root / key
        if target.resolve() != target:
            raise ValueError("Unexpected linked storage path")
        return target

    def _make_parent(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def discard(self, *keys: str):
        for key in keys:
            try:
                self.path(key).unlink(missing_ok=True)
            except OSError:
                # The orphan check can recover a file after an I/O failure.
                continue

    def publish(self, temporary: str, final: str):
        source, destination = self.path(temporary), self.path(final)
        self._make_parent(destination)
        os.utime(source, None)
        source.replace(destination)

    def _encode(self, file, original: str, thumbnail: str):
        try:
            file.seek(0)
            with Image.open(file, formats=SUPPORTED) as image:
                if image.width * image.height > self.settings.image_max_pixels:
                    raise ApiError(413, "image_pixels", "图片像素超过限制。")
                if getattr(image, "n_frames", 1) != 1:
                    raise ApiError(415, "image_format", "请选择单帧 JPEG、PNG 或 WebP。")
                image.verify()
            file.seek(0)
            with Image.open(file, formats=SUPPORTED) as image:
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail((self.settings.image_max_edge,) * 2, Image.Resampling.LANCZOS)
                width, height = image.size
                mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
                normalized = image.convert(mode)
        except Image.DecompressionBombError:
            raise ApiError(413, "image_pixels", "图片像素超过限制。") from None
        except (UnidentifiedImageError, SyntaxError, ValueError, OSError):
            raise ApiError(415, "image_format", "文件不是有效的 JPEG、PNG 或 WebP。") from None
        with normalized:
            normalized.info.clear()
            normalized.save(original, "WEBP", quality=86)
            normalized.thumbnail((self.settings.image_thumbnail_edge,) * 2, Image.Resampling.LANCZOS)
            normalized.save(thumbnail, "WEBP", quality=81)
        return width, height

    def create(self, db: Session, owner: str, file):
        if not self.slots.acquire(blocking=False):
            raise ApiError(429, "image_busy", "正在处理其他图片，请稍后重试。", {"Retry-After": "1"})
        identifier = uuid4()
        stem = identifier.hex
        original = f"originals/{stem}.webp"
        thumbnail = f"thumbnails/{stem}.webp"
        temp_original = f"staging/{stem}-original.webp"
        temp_thumbnail = f"staging/{stem}-thumbnail.webp"
        try:
            original_file, thumbnail_file = self.path(temp_original), self.path(temp_thumbnail)
            self._make_parent(original_file)
            width, height = self._encode(file, original_file, thumbnail_file)
            size, thumb_size = original_file.stat().st_size, thumbnail_file.stat().st_size
            with original_file.open("rb") as source:
                digest = file_digest(source, "sha256").hexdigest()
            lock_owner(db, owner)
            count, byte_sum = db.execute(select(
                func.count(MediaAsset.id), func.coalesce(func.sum(MediaAsset.size_bytes + MediaAsset.thumbnail_size_bytes), 0),
            ).where(MediaAsset.user_id == owner)).one()
            if count >= self.settings.media_user_files or byte_sum + size + thumb_size > self.settings.media_user_bytes:
                raise ApiError(413, "media_quota", "图片存储额度已用完。")
            asset = MediaAsset(id=str(identifier), user_id=owner, original_key=original, thumbnail_key=thumbnail,
                               content_type="image/webp", size_bytes=size, thumbnail_size_bytes=thumb_size,
                               width=width, height=height, sha256=digest)
            db.add(asset)
            db.flush()
            self.publish(temp_original, original)
            self.publish(temp_thumbnail, thumbnail)
            db.commit()
            return asset
        except Exception:
            db.rollback()
            # Never remove a file whose database commit actually succeeded.
            if self.path(original).exists() or self.path(thumbnail).exists():
                try:
                    if db.get(MediaAsset, str(identifier)) is None:
                        self.discard(original, thumbnail)
                finally:
                    db.rollback()
            raise
        finally:
            self.discard(temp_original, temp_thumbnail)
            self.slots.release()

    def remove(self, db: Session, owner: str, media_id: str):
        lock_owner(db, owner)
        asset = owned_media(db, owner, media_id)
        if db.scalar(select(referenced(asset.id))):
            raise ApiError(409, "media_in_use", "请先从用餐记录中移除这张图片。")
        if db.scalar(select(used_by_ai(asset.id, utcnow()))):
            raise ApiError(409, "media_in_ai_use", "这张照片正在识别，请先取消或等待任务结束。")
        keys = asset.original_key, asset.thumbnail_key
        db.delete(asset)
        db.commit()
        self.discard(*keys)

    def sweep(self, db: Session, *, apply: bool = False):
        now = utcnow()
        cutoff = now - timedelta(seconds=self.settings.media_orphan_seconds)
        rows = db.execute(select(MediaAsset.id, MediaAsset.user_id).where(
            MediaAsset.status == "draft", MediaAsset.updated_at < cutoff, ~referenced(MediaAsset.id),
            ~used_by_ai(MediaAsset.id, now),
        )).all()
        db.rollback()
        removed_assets = 0
        for media_id, owner in rows:
            if not apply:
                removed_assets += 1
                continue
            lock_owner(db, owner)
            asset = db.scalar(select(MediaAsset).where(
                MediaAsset.id == media_id, MediaAsset.user_id == owner, MediaAsset.status == "draft",
                MediaAsset.updated_at < cutoff, ~referenced(MediaAsset.id), ~used_by_ai(MediaAsset.id, utcnow()),
            ))
            if asset:
                keys = asset.original_key, asset.thumbnail_key
                db.execute(delete(MediaAsset).where(MediaAsset.id == media_id))
                db.commit()
                self.discard(*keys)
                removed_assets += 1
            else:
                db.rollback()

        orphan_files = 0
        for folder in ("originals", "thumbnails", "staging"):
            directory = self.root / folder
            if not directory.is_dir() or directory.resolve() != directory:
                continue
            for path in directory.glob("*.webp"):
                key = path.relative_to(self.root).as_posix()
                if not FILE_KEY.fullmatch(key) or path.is_symlink() or not path.is_file():
                    continue
                try:
                    if path.stat().st_mtime >= cutoff.timestamp():
                        continue
                except FileNotFoundError:
                    continue
                if db.scalar(select(MediaAsset.id).where(
                    (MediaAsset.original_key == key) | (MediaAsset.thumbnail_key == key),
                )):
                    continue
                orphan_files += 1
                if apply:
                    self.discard(key)
        return {"unreferenced_assets": removed_assets, "untracked_files": orphan_files}
