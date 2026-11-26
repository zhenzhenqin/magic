from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.ai_schemas import AiCapabilities, JobCreate, JobRetry, JobView, UsageView
from app.api.diary import IdempotencyKey
from app.core.database import utcnow
from app.dependencies import CurrentUser, Database
from app.services import ai_jobs

router = APIRouter(prefix="/ai", tags=["食物识别"])


@router.get("/capabilities")
def capabilities(request: Request, user: CurrentUser, db: Database) -> AiCapabilities:
    return ai_jobs.capabilities(db, request.app.state.settings)


@router.get("/usage")
def usage(request: Request, user: CurrentUser, db: Database) -> UsageView:
    return ai_jobs.usage(db, request.app.state.settings, user.id, utcnow())


@router.post("/jobs", status_code=202)
def create(request: Request, data: JobCreate, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    return ai_jobs.view_job(db, ai_jobs.create_job(db, settings, user.id, key, data), settings)


RecoveryKey = Annotated[str | None, Query(pattern=r"^[a-z0-9_-]{8,128}$")]


@router.get("/jobs/recover")
def recover(request: Request, user: CurrentUser, db: Database, request_key: RecoveryKey = None,
            retry_key: RecoveryKey = None, form_meal_id: UUID | None = None, job_id: UUID | None = None) -> JobView | None:
    return ai_jobs.recover_job(db, request.app.state.settings, user.id, request_key=request_key, retry_key=retry_key,
                               form_meal_id=str(form_meal_id) if form_meal_id else None,
                               job_id=str(job_id) if job_id else None)


@router.get("/jobs/{job_id}")
def detail(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(db, ai_jobs.owned_job(db, user.id, str(job_id)), request.app.state.settings)


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(db, ai_jobs.cancel_job(db, user.id, str(job_id)), request.app.state.settings)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(request: Request, job_id: UUID, data: JobRetry, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    return ai_jobs.view_job(db, ai_jobs.retry_job(db, settings, user.id, str(job_id), key, data), settings)
