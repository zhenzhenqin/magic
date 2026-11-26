from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.ai_schemas import AiCapabilities, JobCreate, JobRetry, JobView, UsageView
from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models.ai import AiJob, AiJobMedia, AiRetryRequest, AiUsageLog
from app.models.diary import Meal, MediaAsset
from app.services.ai_control import cumulative_exhausted, worker_online
from app.services.ai_prompt import CONSENT_VERSION, PRIVACY_URL, PROMPT_VERSION
from app.services.storage import MEDIA_MISSING, lock_owner

ACTIVE = ("pending", "running")
RETRYABLE = {"ai_before_send", "ai_rate_limited", "ai_invalid_result", "ai_result_unknown", "ai_quota"}


def capabilities(db: Session, settings: Settings) -> AiCapabilities:
    return AiCapabilities(available=settings.ai_available, simulated=settings.ai_provider == "fake",
                          max_images=settings.ai_max_images, consent_version=CONSENT_VERSION,
                          privacy_url=PRIVACY_URL if settings.ai_provider == "qwen" else None,
                          worker_online=worker_online(db, settings, utcnow()))


def owned_job(db: Session, owner: str, job_id: str) -> AiJob:
    job = db.scalar(select(AiJob).where(AiJob.user_id == owner, AiJob.id == job_id))
    if job is None:
        raise ApiError(404, "ai_job_not_found", "识别任务不存在或不可访问。")
    return job


def configuration_matches(settings: Settings, job: AiJob) -> bool:
    return (settings.ai_available and job.provider == settings.ai_provider and job.model == settings.ai_model_name
            and job.prompt_version == PROMPT_VERSION and job.consent_version == CONSENT_VERSION)


def request_fingerprint(data: JobCreate) -> str:
    return sha256(data.model_dump_json(exclude_none=True).encode()).hexdigest()


def matching_photos(job: AiJob, ids: list[str]) -> bool:
    if not ids or (job.media_snapshot is not None and job.media_snapshot != ids):
        return False
    try:
        data = JobCreate(media_ids=ids, consent_version=job.consent_version, form_meal_id=job.form_meal_id)
    except ValidationError:
        return False
    return request_fingerprint(data) == job.fingerprint


def linked_photos(db: Session, job: AiJob) -> list[str]:
    return list(db.scalars(select(AiJobMedia.media_id).where(
        AiJobMedia.job_id == job.id, AiJobMedia.user_id == job.user_id,
    ).order_by(AiJobMedia.sort_order)))


def recover_job(db: Session, settings: Settings, owner: str, *, request_key=None, retry_key=None,
                form_meal_id=None, job_id=None) -> JobView | None:
    query = select(AiJob).where(AiJob.user_id == owner)
    if job_id:
        query = query.where(AiJob.id == job_id)
    if request_key:
        query = query.where(AiJob.request_key == request_key)
    elif retry_key:
        query = query.join(AiRetryRequest, (AiRetryRequest.job_id == AiJob.id)
                           & (AiRetryRequest.user_id == AiJob.user_id)).where(AiRetryRequest.key == retry_key)
    else:
        now = utcnow()
        cutoff = now - timedelta(seconds=settings.ai_job_retention_seconds)
        active = AiJob.status.in_(ACTIVE) & ((AiJob.expires_at > now) | (AiJob.lease_until > now))
        query = query.where(
            active
            | ((AiJob.status.in_(("succeeded", "failed"))) & (AiJob.completed_at > cutoff)
               & (AiJob.adopted_meal_id.is_(None)) & (AiJob.form_meal_id == form_meal_id)),
        ).order_by(case((active, 0), else_=1), AiJob.updated_at.desc())
    job = db.scalar(query.limit(1))
    if not job or (job.completed_at and job.completed_at <= utcnow() - timedelta(seconds=settings.ai_job_retention_seconds)):
        return None
    return view_job(db, job, settings)


def view_job(db: Session, job: AiJob, settings: Settings) -> JobView:
    now = utcnow()
    status, error = job.status, job.error_code
    if job.expires_at <= now and (status == "pending" or (status == "running" and job.lease_until <= now)):
        status, error = "failed", "ai_expired"
    if job.completed_at and job.completed_at + timedelta(seconds=settings.ai_job_retention_seconds) <= now:
        raise ApiError(404, "ai_job_not_found", "识别任务不存在或不可访问。")
    can_retry = (status == "failed" and error in RETRYABLE and job.attempt_count < job.max_attempts
                 and job.expires_at > now and configuration_matches(settings, job))
    ids = linked_photos(db, job)
    return JobView(id=job.id, status=status, simulated=job.provider == "fake", result=job.result_json,
                   error_code=error, can_retry=can_retry, attempt_count=job.attempt_count,
                   created_at=job.created_at, expires_at=job.expires_at,
                   media_ids=ids if matching_photos(job, ids) else [], form_meal_id=job.form_meal_id,
                   worker_online=worker_online(db, settings, now))


def usage(db: Session, settings: Settings, owner: str, now, *, exclude: str = "") -> UsageView:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total, user_total = db.execute(select(
        func.count(), func.count().filter(AiUsageLog.user_id == owner),
    ).where(AiUsageLog.created_at >= start, AiUsageLog.provider == settings.ai_provider,
            AiUsageLog.status != "not_sent", AiUsageLog.id != exclude)).one()
    reason = None
    if cumulative_exhausted(db, settings):
        reason = "ai_cumulative_limit"
    elif total >= settings.ai_global_daily_limit or user_total >= settings.ai_user_daily_limit:
        reason = "ai_quota"
    return UsageView(used=user_total, limit=settings.ai_user_daily_limit, resets_at=start + timedelta(days=1),
                     available=settings.ai_available and reason is None, exhausted_reason=reason)


def quota_error(reason: str | None):
    if reason == "ai_cumulative_limit":
        return ApiError(429, reason, "真实模型联调累计额度已用完，仍可手动记录。")
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
    quota = usage(db, settings, owner, now)
    if not quota.available:
        raise quota_error(quota.exhausted_reason)


def create_job(db: Session, settings: Settings, owner: str, key: str, data: JobCreate) -> AiJob:
    lock_owner(db, owner)  # The first SQLite write serializes ownership, quota and idempotency decisions.
    digest = request_fingerprint(data)
    existing = db.scalar(select(AiJob).where(AiJob.user_id == owner, AiJob.request_key == key))
    if existing:
        if existing.fingerprint != digest:
            raise ApiError(409, "idempotency_conflict", "同一请求标识不能用于不同照片。")
        return existing
    require_consent(settings, data.consent_version)
    form_meal_id = str(data.form_meal_id) if data.form_meal_id else None
    if form_meal_id and not db.scalar(select(Meal.id).where(Meal.id == form_meal_id, Meal.user_id == owner)):
        raise ApiError(404, "meal_not_found", "用餐记录不存在或不可访问。")
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
                form_meal_id=form_meal_id, media_snapshot=ids,
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
            attempt.status, attempt.error_code = "not_sent", "ai_cancelled"
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
    if not view_job(db, job, settings).can_retry:
        raise ApiError(409, "ai_cannot_retry", "此识别任务无法重试，可以手动记录。")
    if job.error_code == "ai_result_unknown" and not data.accept_unknown_charge:
        raise ApiError(409, "ai_retry_confirmation", "上次调用可能已经计费，请确认是否再次识别。")
    if not matching_photos(job, linked_photos(db, job)):
        raise ApiError(409, "ai_images_expired", "识别所用照片已移除，请重新选择照片。")
    now = utcnow()
    require_slot(db, settings, owner, now)
    retry_later(job, now, 0, None)
    db.add(AiRetryRequest(user_id=owner, job_id=job_id, key=key, fingerprint=digest))
    db.commit()
    return job
