from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, StrictBool, StringConstraints, model_validator

from app.dependencies import CurrentUser, Database
from app.diary_schemas import MealType
from app.schemas import Input
from app.services import catalog

router = APIRouter(prefix="/catalog", tags=["个人美食图鉴"])
Page = Annotated[int, Query(ge=1, le=10_000)]
Limit = Annotated[int, Query(ge=1, le=50)]


class Entry(BaseModel):
    id: UUID
    canonical_name: str
    display_name: str
    category: str | None
    cover_media_id: UUID | None
    cover_use_original: bool
    cover_whole_meal: bool
    is_favorite: bool
    first_eaten: date | None
    last_eaten: date | None
    occasions: int
    details: int


class CatalogPage(BaseModel):
    items: list[Entry]
    total: int
    page: int
    limit: int
    collected: int
    categories: list[str]


class Edit(Input):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    cover_media_id: UUID | None = None
    is_favorite: StrictBool | None = None

    @model_validator(mode="after")
    def fields(self):
        for name in ("display_name", "is_favorite"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class Merge(Input):
    source_id: UUID
    target_id: UUID


class HistoryItem(BaseModel):
    meal_id: UUID
    local_date: date
    meal_type: MealType
    eaten_at: datetime
    media_ids: list[UUID]


class History(BaseModel):
    items: list[HistoryItem]
    total: int
    page: int
    limit: int


@router.get("")
def index(user: CurrentUser, db: Database, search: Annotated[str, Query(max_length=80)] = "",
          category: Annotated[str, Query(max_length=40)] = "", favorites: bool = False,
          sort: Literal["recent", "occasions"] = "recent", page: Page = 1, limit: Limit = 24) -> CatalogPage:
    return catalog.list_catalog(db, user.id, search.strip(), category, favorites, sort, page, limit)


@router.post("/merge")
def merge(user: CurrentUser, db: Database, data: Merge) -> Entry:
    return catalog.merge(db, user.id, str(data.source_id), str(data.target_id))


@router.get("/{identifier}")
def detail(user: CurrentUser, db: Database, identifier: UUID) -> Entry:
    return catalog.detail(db, user.id, str(identifier))


@router.patch("/{identifier}")
def edit(user: CurrentUser, db: Database, identifier: UUID, data: Edit) -> Entry:
    return catalog.edit(db, user.id, str(identifier), data.model_dump(exclude_unset=True))


@router.get("/{identifier}/history")
def history(user: CurrentUser, db: Database, identifier: UUID, page: Page = 1, limit: Limit = 12) -> History:
    return catalog.history(db, user.id, str(identifier), page, limit)
