import json
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models.stickers import MediaDerivative, StickerJob, StickerRuntime
from app.services.sticker_image import MODEL, MODEL_SHA256, PROCESSING_VERSION
from app.services.storage import lock_owner, owned_media

MAX_ATTEMPTS = 2
HEARTBEAT_AGE = 15


def model_directory(settings):
    return settings.sticker_model_dir.resolve()


def model_files_available(settings):
    return settings.sticker_provider == "fake" or (model_directory(settings) / f"{MODEL}.onnx").is_file()


def online(db, settings):
    row = db.get(StickerRuntime, 1)
    return bool(settings.sticker_enabled and model_files_available(settings) and row
                and row.heartbeat >= utcnow() - timedelta(seconds=HEARTBEAT_AGE))


def configuration(settings, crop):
    name, version = ("manual-crop", "1") if crop else (
        ("fake", "test-v1") if settings.sticker_provider == "fake" else (MODEL, MODEL_SHA256)
    )
    payload = (name, version, PROCESSING_VERSION, settings.sticker_edge, settings.image_thumbnail_edge, crop)
    return name, version, sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def derivative(db, owner, media_id):
    return db.scalar(select(MediaDerivative).where(
        MediaDerivative.user_id == owner, MediaDerivative.source_media_id == media_id, MediaDerivative.status == "ready",
    ))


def by_source(db, owner, media_id):
    return db.scalar(select(StickerJob).where(StickerJob.user_id == owner, StickerJob.source_media_id == media_id))


def owned_job(db, owner, identifier):
    row = db.scalar(select(StickerJob).where(StickerJob.user_id == owner, StickerJob.id == identifier))
    if row is None:
        raise ApiError(404, "sticker_not_found", "贴纸任务不存在或不可访问。")
    return row


def public(db, job):
    result = derivative(db, job.user_id, job.source_media_id)
    return dict(id=job.id, media_id=job.source_media_id, status=job.status, error_code=job.error_code,
                attempts=job.attempts, ready=result is not None,
                manual=bool(job.crop), result_id=result.id if result else None)


def queue(db, settings, storage, owner, media_id, crop=None, *, force=False):
    lock_owner(db, owner)
    asset = owned_media(db, owner, media_id)
    job = by_source(db, owner, media_id)
    now = utcnow()
    _, _, recipe = configuration(settings, crop)
    result = derivative(db, owner, media_id)
    same_result = result and result.recipe == recipe and result.source_digest == asset.sha256 and all(
        storage.path(key).is_file() for key in (result.storage_key, result.cutout_key, result.thumbnail_key)
    )
    unchanged = job and job.recipe == recipe and job.source_digest == asset.sha256
    if job and not force and (job.status in ("pending", "running") or same_result or (unchanged and job.status != "succeeded")):
        return public(db, job)
    if not online(db, settings):
        raise ApiError(503, "sticker_worker_unavailable", "贴纸制作暂不可用，可以先保存原图。")
    if job and job.claim and job.lease_until and job.lease_until > now:
        raise ApiError(409, "sticker_job_busy", "请等待上一项处理结束。")
    active = db.scalar(select(func.count()).select_from(StickerJob).where(
        StickerJob.user_id == owner, StickerJob.status.in_(("pending", "running")),
    ))
    if active >= settings.sticker_pending_per_user:
        raise ApiError(429, "sticker_queue_full", "还有照片在处理，请稍后再试。")
    if job is None:
        job = StickerJob(id=str(uuid4()), user_id=owner, source_media_id=media_id)
        db.add(job)
    job.recipe, job.source_digest, job.crop = recipe, asset.sha256, crop
    job.status, job.attempts, job.claim, job.lease_until, job.error_code, job.updated_at = "pending", 0, None, None, None, now
    db.flush()
    response = public(db, job)
    db.commit()
    return response


def cancel(db, owner, identifier):
    lock_owner(db, owner)
    job = owned_job(db, owner, identifier)
    if job.status in ("pending", "running"):
        job.status, job.updated_at = "cancelled", utcnow()
    response = public(db, job)
    db.commit()
    return response


def retry(db, settings, storage, owner, identifier, crop=None):
    lock_owner(db, owner)
    job = owned_job(db, owner, identifier)
    return queue(db, settings, storage, owner, job.source_media_id, crop, force=True)
