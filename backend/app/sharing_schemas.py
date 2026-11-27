from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, StringConstraints

from app.diary_schemas import MealType, NutrientSummary
from app.schemas import Input

PublicId = Annotated[str, StringConstraints(pattern=r"^fd_[0-9a-f]{32}$")]
HistoryScope = Literal["today", "week", "month", "all"]
RequestStatus = Literal["pending", "accepted", "rejected", "cancelled"]
MediaKind = Literal["photo", "sticker"]


class Person(BaseModel):
    public_id: PublicId
    nickname: str


class ShareFlags(Input):
    records: StrictBool = False
    names: StrictBool = False
    photos: StrictBool = False
    stickers: StrictBool = False
    catalog: StrictBool = False
    calories: StrictBool = False
    nutrition: StrictBool = False
    notes: StrictBool = False
    history: StrictBool = False


class Grant(BaseModel):
    permissions: ShareFlags
    history_scope: HistoryScope
    history_start: date | None
    granted_at: datetime | None
    version: int


class Friend(BaseModel):
    relationship_id: UUID
    person: Person
    outgoing: Grant
    incoming: Grant


class FriendList(BaseModel):
    me: Person
    items: list[Friend]


class RequestCreate(Input):
    public_id: PublicId


class RequestView(BaseModel):
    id: UUID
    person: Person
    direction: Literal["incoming", "outgoing"]
    status: RequestStatus
    created_at: datetime


class GrantEdit(Input):
    relationship_id: UUID
    version: Annotated[int, Field(ge=0)]
    permissions: ShareFlags
    history_scope: HistoryScope | None = None


class SharedMedia(BaseModel):
    id: UUID
    kinds: list[MediaKind]


class SharedItem(BaseModel):
    food_name: str | None = None
    category: str | None = None
    calories_kcal: float | None = None
    weight_g: float | None = None
    protein_g: float | None = None
    carbohydrates_g: float | None = None
    fat_g: float | None = None
    note: str | None = None
    estimated: bool | None = None


class SharedMeal(BaseModel):
    id: UUID
    local_date: date
    local_time: str
    meal_type: MealType
    items: list[SharedItem] | None = None
    media: list[SharedMedia] | None = None
    note: str | None = None


class SharedMeals(BaseModel):
    items: list[SharedMeal]
    total: int
    page: int
    limit: int


class SharedCalendarDay(BaseModel):
    date: date
    meals: int
    media: SharedMedia | None = None
    meal_id: UUID | None = None


class SharedCalendar(BaseModel):
    month: str
    days: list[SharedCalendarDay]


class SharedNutrient(NutrientSummary):
    estimated: bool


class SharedDaily(BaseModel):
    date: date
    meals: int
    nutrition: dict[str, SharedNutrient] | None = None


class SharedFood(BaseModel):
    id: str
    name: str
    category: str | None
    cover: SharedMedia | None = None
    cover_whole_meal: bool | None = None
    occurrences: int | None = None
    items: int | None = None
    first_eaten: date | None = None
    last_eaten: date | None = None


class SharedFoods(BaseModel):
    names_shared: bool
    items: list[SharedFood]
    page: int
    limit: int
    total: int | None = None
    categories: list[str] | None = None


class SharedHistoryItem(BaseModel):
    id: UUID
    local_date: date
    meal_type: MealType


class SharedHistory(BaseModel):
    items: list[SharedHistoryItem]
    total: int
    page: int
    limit: int
