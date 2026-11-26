from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_schemas import AiCapabilities, JobCreate, JobRetry, JobView, UsageView
from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models.ai import AiJob, AiJobMedia, AiRetryRequest, AiUsageLog
from app.models.diary import MediaAsset
from app.services.ai_prompt import CONSENT_VERSION, PRIVACY_URL, PROMPT_VERSION
from app.services.storage import MEDIA_MISSING, lock_owner

ACTIVE = ("pending", "running")
RETRYABLE = {"ai_before_send", "ai_rate_limited", "ai_invalid_result", "ai_result_unknown", "ai_quota"}


def capabilities(settings: Settings) -> AiCapabilities:
    return AiCapabilities(available=settings.ai_available, simulated=settings.ai_provider == "fake",
                          max_images=settings.ai_max_images, consent_version=CONSENT_VERSION,
                          privacy_url=PRIVACY_URL if settings.ai_provider == "qwen" else None)


def owned_job(db: Session, owner: str, job_id: str) -> AiJob:
    job = db.scalar(select(AiJob).where(AiJob.user_id == owner, AiJob.id == job_id))
    if job is None:
        raise ApiError(404, "ai_job_not_found", "识别任务不存在或不可访问。")
    return job


def configuration_matches(settings: Settings, job: AiJob) -> bool:
    return (settings.ai_available and job.provider == settings.ai_provider and job.model == settings.ai_model_name
            and job.prompt_version == PROMPT_VERSION and job.consent_version == CONSENT_VERSION)


def view_job(job: AiJob, settings: Settings) -> JobView:
    now = utcnow()
    status, error = job.status, job.error_code
    if job.expires_at <= now and (status == "pending" or (status == "running" and job.lease_until <= now)):
        status, error = "failed", "ai_expired"
    if job.completed_at and job.completed_at + timedelta(seconds=settings.ai_job_retention_seconds) <= now:
        raise ApiError(404, "ai_job_not_found", "识别任务不存在或不可访问。")
    can_retry = (status == "failed" and error in RETRYABLE and job.attempt_count < job.max_attempts
                 and job.expires_at > now and configuration_matches(settings, job))
    return JobView(id=job.id, status=status, simulated=job.provider == "fake", result=job.result_json,
                   error_code=error, can_retry=can_retry, attempt_count=job.attempt_count,
                   created_at=job.created_at, expires_at=job.expires_at)


def usage(db: Session, settings: Settings, owner: str, now, *, exclude: str = "") -> UsageView:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total, user_total = db.execute(select(
        func.count(), func.count().filter(AiUsageLog.user_id == owner),
    ).where(AiUsageLog.created_at >= start, AiUsageLog.provider == settings.ai_provider,
            AiUsageLog.status != "not_sent", AiUsageLog.id != exclude)).one()
    return UsageView(used=user_total, limit=settings.ai_user_daily_limit, resets_at=start + timedelta(days=1),
                     available=settings.ai_available and total < settings.ai_global_daily_limit
                     and user_total < settings.ai_user_daily_limit)


def quota_error():
    return ApiError(429, "ai_quota", "今天的识别额度已用完，仍可手动记录。")


def require_consent(settings: Settings, version: str):
    if not settings.ai_available:
        raise ApiError(503, "ai_unavailable", "AI 识别暂不可用，你仍可以手动记录。")
    if version != CONSENT_VERSION:
        raise ApiError(409, "ai_consent_required", "请重新查看照片处理说明并确认。")


def require_slot(db: Session, settings: Settings, owner: str, now):
    other = db.scalar(select(AiJob.id).where(
        AiJob.user_id == owner, AiJob.status.in_(ACTIVE),
        (AiJob.status == "running") | (AiJob.expires_at > now),
    ).limit(1))
    if other:
        raise ApiError(409, "ai_job_active", "已有一项识别正在处理，请稍后再试。")
    if not usage(db, settings, owner, now).available:
        raise quota_error()


def create_job(db: Session, settings: Settings, owner: str, key: str, data: JobCreate) -> AiJob:
    lock_owner(db, owner)  # The first SQLite write serializes ownership, quota and idempotency decisions.
    digest = sha256(data.model_dump_json().encode()).hexdigest()
    existing = db.scalar(select(AiJob).where(AiJob.user_id == owner, AiJob.request_key == key))
    if existing:
        if existing.fingerprint != digest:
            raise ApiError(409, "idempotency_conflict", "同一请求标识不能用于不同照片。")
        return existing
    require_consent(settings, data.consent_version)
    ids = [str(identifier) for identifier in data.media_ids]
    if len(ids) > settings.ai_max_images:
        raise ApiError(422, "ai_image_count", "所选识别照片超过数量限制。")
    valid = set(db.scalars(select(MediaAsset.id).where(MediaAsset.user_id == owner, MediaAsset.id.in_(ids))))
    if valid != set(ids):
        raise ApiError(404, "media_not_found", MEDIA_MISSING)
    now = utcnow()
    require_slot(db, settings, owner, now)
    job = AiJob(id=str(uuid4()), user_id=owner, request_key=key, fingerprint=digest,
                provider=settings.ai_provider, model=settings.ai_model_name, prompt_version=PROMPT_VERSION,
                consent_version=CONSENT_VERSION, max_attempts=settings.ai_max_attempts,
                available_at=now, expires_at=now + timedelta(seconds=settings.ai_job_ttl_seconds),
                created_at=now, updated_at=now)
    db.add(job)
    db.flush()
    db.add_all(AiJobMedia(user_id=owner, job_id=job.id, media_id=media_id, sort_order=index)
               for index, media_id in enumerate(ids))
    db.commit()
    return job


def end_job(job: AiJob, status: str, now, code: str | None = None):
    job.status, job.error_code, job.completed_at = status, code, now
    job.claim_token = job.lease_until = None
    job.updated_at = now


def retry_later(job: AiJob, now, delay: int, code: str | None):
    job.status, job.error_code, job.available_at = "pending", code, now + timedelta(seconds=delay)
    job.claim_token = job.lease_until = job.completed_at = None
    job.updated_at = now


def cancel_job(db: Session, owner: str, job_id: str) -> AiJob:
    lock_owner(db, owner)
    job = owned_job(db, owner, job_id)
    if job.status in ACTIVE:
        attempt = db.get(AiUsageLog, job.claim_token) if job.claim_token else None
        if attempt and attempt.status == "reserved":
            attempt.status = "not_sent"
        end_job(job, "cancelled", utcnow())
        db.commit()
    return job


def retry_job(db: Session, settings: Settings, owner: str, job_id: str, key: str, data: JobRetry) -> AiJob:
    lock_owner(db, owner)
    job = owned_job(db, owner, job_id)
    digest = sha256(data.model_dump_json().encode()).hexdigest()
    replay = db.get(AiRetryRequest, (owner, job_id, key))
    if replay:
        if replay.fingerprint != digest:
            raise ApiError(409, "idempotency_conflict", "同一重试标识不能用于不同确认内容。")
        return job
    require_consent(settings, data.consent_version)
    if not view_job(job, settings).can_retry:
        raise ApiError(409, "ai_cannot_retry", "此识别任务无法重试，可以手动记录。")
    if job.error_code == "ai_result_unknown" and not data.accept_unknown_charge:
        raise ApiError(409, "ai_retry_confirmation", "上次调用可能已经计费，请确认是否再次识别。")
    identifiers = list(db.scalars(select(AiJobMedia.media_id).where(
        AiJobMedia.job_id == job_id, AiJobMedia.user_id == owner,
    ).order_by(AiJobMedia.sort_order)))
    # The original fingerprint also detects a partial deletion of the selected photos.
    original = JobCreate(media_ids=identifiers, consent_version=job.consent_version) if identifiers else None
    if original is None or sha256(original.model_dump_json().encode()).hexdigest() != job.fingerprint:
        raise ApiError(409, "ai_images_expired", "识别所用照片已移除，请重新选择照片。")
    now = utcnow()
    require_slot(db, settings, owner, now)
    retry_later(job, now, 0, None)
    db.add(AiRetryRequest(user_id=owner, job_id=job_id, key=key, fingerprint=digest))
    db.commit()
    return job
