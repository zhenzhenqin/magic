from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import func, select
import re

from app.ai_schemas import AiCapabilities, JobCreate, JobRetry, JobView, UsageView
from app.api.diary import IdempotencyKey
from app.core.database import utcnow
from app.core.exceptions import ApiError, invalid_session
from app.dependencies import CurrentUser, Database
from app.models import UserSettings
from app.models.ai import AiUsageLog
from app.schemas import Input
from app.services import ai_jobs
from app.services.ai_credentials import active_session
from app.services.ai_provider import ProviderError, simulated_balance
from app.services.storage import lock_owner

router = APIRouter(prefix="/ai", tags=["食物识别"])


class Connect(Input):
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def local_key(cls, value):
        if not re.fullmatch(r"fd-test-[A-Za-z0-9_-]{8,80}", value.get_secret_value()):
            raise ValueError("Only an offline test key can be used")
        return value


class Preferences(Input):
    daily_limit: int | None = Field(default=None, ge=0, le=1000, strict=True)
    dismiss_intro: bool = False


def personal(request, db, owner):
    settings = request.app.state.settings
    preferences = db.get(UserSettings, owner)
    credential = request.app.state.ai_credentials.get(owner, request.state.auth_session_id)
    end = utcnow()
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    today, total, input_tokens, output_tokens, unknown = db.execute(select(
        func.count().filter(AiUsageLog.created_at >= start), func.count(),
        func.sum(AiUsageLog.input_tokens), func.sum(AiUsageLog.output_tokens),
        func.count().filter(AiUsageLog.status == "unknown"),
    ).where(AiUsageLog.user_id == owner, AiUsageLog.credential_ref.is_not(None),
            AiUsageLog.status.in_(("succeeded", "failed", "unknown", "dispatching")))).one()
    return {
        "mode": "simulation" if settings.ai_byok_simulation and settings.ai_available else "disabled",
        "connected": credential is not None, "expires_at": credential.expires_at if credential else None,
        "maximum_daily_limit": settings.ai_user_daily_limit, "daily_limit": preferences.ai_daily_limit,
        "intro_dismissed": preferences.ai_intro_dismissed, "today": today, "total": total,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "unknown": unknown,
    }


@router.get("/connection")
def connection(request: Request, user: CurrentUser, db: Database):
    return personal(request, db, user.id)


@router.put("/connection")
def connect(request: Request, data: Connect, user: CurrentUser, db: Database):
    settings = request.app.state.settings
    if not settings.ai_byok_simulation or not settings.ai_available:
        raise ApiError(503, "ai_connection_disabled", "个人 AI 真实调用尚未开放。")
    lock_owner(db, user.id)
    session = active_session(db, user.id, request.state.auth_session_id)
    if session is None:
        raise invalid_session()
    request.app.state.ai_credentials.connect(user.id, session.id, data.api_key, settings.ai_temporary_seconds, session.expires_at)
    db.commit()
    return personal(request, db, user.id)


@router.delete("/connection", status_code=204)
def disconnect(request: Request, user: CurrentUser, db: Database):
    lock_owner(db, user.id)
    if active_session(db, user.id, request.state.auth_session_id) is None:
        raise invalid_session()
    request.app.state.ai_credentials.remove(user.id, request.state.auth_session_id)
    db.commit()


@router.post("/connection/balance")
def balance(request: Request, user: CurrentUser):
    settings = request.app.state.settings
    credential = request.app.state.ai_credentials.get(user.id, request.state.auth_session_id)
    if not settings.ai_byok_simulation or credential is None:
        raise ApiError(409, "ai_credential_required", "请先连接当前会话的个人 AI。")
    try:
        available = simulated_balance(credential)
    except ProviderError as error:
        raise ApiError(503, error.code, "暂时无法验证连接。") from None
    return {"simulated": True, "is_available": available, "balance_infos": []}


@router.patch("/preferences")
def preferences(request: Request, data: Preferences, user: CurrentUser, db: Database):
    lock_owner(db, user.id)
    if active_session(db, user.id, request.state.auth_session_id) is None:
        raise invalid_session()
    record = db.get(UserSettings, user.id)
    if "daily_limit" in data.model_fields_set:
        if data.daily_limit is not None and data.daily_limit > request.app.state.settings.ai_user_daily_limit:
            raise ApiError(422, "ai_limit_range", "个人额度不能超过服务上限。")
        record.ai_daily_limit = data.daily_limit
    if data.dismiss_intro:
        record.ai_intro_dismissed = True
    db.commit()
    return personal(request, db, user.id)


@router.get("/capabilities")
def capabilities(request: Request, user: CurrentUser, db: Database) -> AiCapabilities:
    settings = request.app.state.settings
    connected = not settings.ai_byok_simulation or bool(request.app.state.ai_credentials.get(user.id, request.state.auth_session_id))
    return ai_jobs.capabilities(db, settings, connected)


@router.get("/usage")
def usage(request: Request, user: CurrentUser, db: Database) -> UsageView:
    settings = request.app.state.settings
    result = ai_jobs.usage(db, settings, user.id, utcnow())
    if settings.ai_byok_simulation and not request.app.state.ai_credentials.get(user.id, request.state.auth_session_id):
        result.available = False
        result.exhausted_reason = "ai_credential_required"
    return result


@router.post("/jobs", status_code=202)
def create(request: Request, data: JobCreate, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    vault = request.app.state.ai_credentials
    job = ai_jobs.create_job(db, settings, user.id, key, data, vault=vault, session_id=request.state.auth_session_id)
    return ai_jobs.view_job(db, job, settings, vault)


RecoveryKey = Annotated[str | None, Query(pattern=r"^[a-z0-9_-]{8,128}$")]


@router.get("/jobs/recover")
def recover(request: Request, user: CurrentUser, db: Database, request_key: RecoveryKey = None,
            retry_key: RecoveryKey = None, form_meal_id: UUID | None = None, job_id: UUID | None = None) -> JobView | None:
    return ai_jobs.recover_job(db, request.app.state.settings, user.id, request_key=request_key, retry_key=retry_key,
                               form_meal_id=str(form_meal_id) if form_meal_id else None,
                               job_id=str(job_id) if job_id else None, vault=request.app.state.ai_credentials)


@router.get("/jobs/{job_id}")
def detail(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(db, ai_jobs.owned_job(db, user.id, str(job_id)), request.app.state.settings, request.app.state.ai_credentials)


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(db, ai_jobs.cancel_job(db, user.id, str(job_id)), request.app.state.settings, request.app.state.ai_credentials)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(request: Request, job_id: UUID, data: JobRetry, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    vault = request.app.state.ai_credentials
    job = ai_jobs.retry_job(db, settings, user.id, str(job_id), key, data, vault=vault, session_id=request.state.auth_session_id)
    return ai_jobs.view_job(db, job, settings, vault)
