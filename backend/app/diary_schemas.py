from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas import Input

MealType = Literal["breakfast", "lunch", "dinner", "snack"]
Nutrient = Annotated[Decimal, Field(ge=0, le=100000, max_digits=8, decimal_places=2, allow_inf_nan=False)]
Food = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
ItemNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
MealNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ItemInput(Input):
    id: UUID | None = None
    ai_reference: "AiReference | None" = None
    food_name: Food
    category: Category | None = None
    weight_g: Nutrient | None = None
    calories_kcal: Nutrient | None = None
    protein_g: Nutrient | None = None
    carbohydrates_g: Nutrient | None = None
    fat_g: Nutrient | None = None
    note: ItemNote = ""


class AiReference(Input):
    job_id: UUID
    candidate_id: UUID


class MealInput(Input):
    meal_type: MealType
    local_date: Annotated[date, Field(ge=date(1900, 1, 1), le=date(2200, 12, 31))]
    local_time: time
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    note: MealNote = ""
    items: Annotated[list[ItemInput], Field(min_length=1, max_length=30)]
    media_ids: Annotated[list[UUID], Field(max_length=5)] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Provide an IANA timezone name") from None
        return value

    @field_validator("local_time")
    @classmethod
    def local_wall_time(cls, value):
        if value.tzinfo is not None:
            raise ValueError("Use a local time without a UTC offset")
        return value

    @model_validator(mode="after")
    def validate_meal(self):
        if len(self.media_ids) != len(set(self.media_ids)):
            raise ValueError("Each image can appear only once per meal")
        wall = datetime.combine(self.local_date, self.local_time)
        if self.eaten_at.astimezone(ZoneInfo(self.timezone)).replace(tzinfo=None) != wall:
            raise ValueError("This local time does not exist in the selected timezone")
        return self

    @property
    def eaten_at(self):
        return datetime.combine(self.local_date, self.local_time, ZoneInfo(self.timezone)).astimezone(UTC)


class MealEdit(MealInput):
    version: Annotated[int, Field(ge=1, le=2_000_000_000)]


class MediaView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_type: str
    size_bytes: int
    thumbnail_size_bytes: int
    width: int
    height: int
    status: Literal["draft", "attached"]
    created_at: datetime


class ItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    food_name: str
    category: str | None
    weight_g: float | None
    calories_kcal: float | None
    protein_g: float | None
    carbohydrates_g: float | None
    fat_g: float | None
    note: str
    sort_order: int
    source: Literal["manual", "ai", "ai_edited"]
    ai_job_id: UUID | None
    ai_candidate_id: UUID | None
    ai_provider: str | None


class MealView(BaseModel):
    id: UUID
    meal_type: MealType
    local_date: date
    local_time: time
    eaten_at: datetime
    timezone: str
    note: str
    items: list[ItemView]
    media: list[MediaView]
    version: int
    created_at: datetime
    updated_at: datetime


class MealPage(BaseModel):
    items: list[MealView]
    page: int
    limit: int
    total: int


class CalendarDay(BaseModel):
    date: date
    meal_count: int
    representative_media_id: UUID | None = None


class CalendarView(BaseModel):
    month: str
    days: list[CalendarDay]


class NutrientSummary(BaseModel):
    value: float | None
    known_items: int
    complete: bool


class DailyView(BaseModel):
    date: date
    meals: int
    items: int
    nutrition: dict[str, NutrientSummary]
