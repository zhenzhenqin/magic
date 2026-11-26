from uuid import UUID

from fastapi import APIRouter, Request

from app.ai_schemas import AiCapabilities, JobCreate, JobRetry, JobView, UsageView
from app.api.diary import IdempotencyKey
from app.core.database import utcnow
from app.dependencies import CurrentUser, Database
from app.services import ai_jobs

router = APIRouter(prefix="/ai", tags=["食物识别"])


@router.get("/capabilities")
def capabilities(request: Request, user: CurrentUser) -> AiCapabilities:
    return ai_jobs.capabilities(request.app.state.settings)


@router.get("/usage")
def usage(request: Request, user: CurrentUser, db: Database) -> UsageView:
    return ai_jobs.usage(db, request.app.state.settings, user.id, utcnow())


@router.post("/jobs", status_code=202)
def create(request: Request, data: JobCreate, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    return ai_jobs.view_job(ai_jobs.create_job(db, settings, user.id, key, data), settings)


@router.get("/jobs/{job_id}")
def detail(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(ai_jobs.owned_job(db, user.id, str(job_id)), request.app.state.settings)


@router.post("/jobs/{job_id}/cancel")
def cancel(request: Request, job_id: UUID, user: CurrentUser, db: Database) -> JobView:
    return ai_jobs.view_job(ai_jobs.cancel_job(db, user.id, str(job_id)), request.app.state.settings)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(request: Request, job_id: UUID, data: JobRetry, user: CurrentUser, db: Database, key: IdempotencyKey) -> JobView:
    settings = request.app.state.settings
    return ai_jobs.view_job(ai_jobs.retry_job(db, settings, user.id, str(job_id), key, data), settings)
