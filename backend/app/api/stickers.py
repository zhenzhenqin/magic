from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from app.dependencies import CurrentUser, Database
from app.schemas import Input
from app.services import stickers
from app.services.storage import owned_media

router = APIRouter(prefix="/stickers", tags=["本地美食贴纸"])


class Crop(Input):
    left: float = Field(ge=0, lt=1)
    top: float = Field(ge=0, lt=1)
    width: float = Field(ge=.03, le=1)
    height: float = Field(ge=.03, le=1)

    @model_validator(mode="after")
    def fits(self):
        if self.left + self.width > 1.00000001 or self.top + self.height > 1.00000001:
            raise ValueError("Crop must fit within the source image")
        return self

    def coords(self):
        return [round(value, 5) for value in (self.left, self.top, self.width, self.height)]


class Create(Input):
    media_id: UUID
    crop: Crop | None = None


class Retry(Input):
    crop: Crop | None = None


class Job(BaseModel):
    id: UUID
    media_id: UUID
    status: Literal["pending", "running", "failed", "succeeded", "cancelled"]
    attempts: int
    error_code: str | None
    ready: bool
    manual: bool
    result_id: UUID | None


class Capabilities(BaseModel):
    online: bool
    enabled: bool
    simulated: bool


@router.get("/capabilities")
def capabilities(request: Request, user: CurrentUser, db: Database) -> Capabilities:
    settings = request.app.state.settings
    return Capabilities(online=stickers.online(db, settings), enabled=settings.sticker_enabled,
                        simulated=settings.sticker_provider == "fake")


@router.post("/jobs", status_code=202)
def create(request: Request, user: CurrentUser, db: Database, data: Create) -> Job:
    return stickers.queue(db, request.app.state.settings, request.app.state.storage, user.id, str(data.media_id),
                          data.crop.coords() if data.crop else None)


@router.get("/sources/{media_id}")
def source(user: CurrentUser, db: Database, media_id: UUID) -> Job | None:
    owned_media(db, user.id, str(media_id))
    row = stickers.by_source(db, user.id, str(media_id))
    return stickers.public(db, row) if row else None


@router.get("/jobs/{identifier}")
def detail(user: CurrentUser, db: Database, identifier: UUID) -> Job:
    return stickers.public(db, stickers.owned_job(db, user.id, str(identifier)))


@router.post("/jobs/{identifier}/retry", status_code=202)
def retry(request: Request, user: CurrentUser, db: Database, identifier: UUID, data: Retry) -> Job:
    return stickers.retry(db, request.app.state.settings, request.app.state.storage, user.id, str(identifier),
                          data.crop.coords() if data.crop else None)


@router.post("/jobs/{identifier}/cancel")
def cancel(user: CurrentUser, db: Database, identifier: UUID) -> Job:
    return stickers.cancel(db, user.id, str(identifier))
