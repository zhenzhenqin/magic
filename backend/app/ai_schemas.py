from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StringConstraints, field_serializer, field_validator, model_validator

from app.diary_schemas import Food
from app.schemas import Input

AiStatus = Literal["pending", "running", "succeeded", "failed", "cancelled"]
RecognitionStatus = Literal["recognized", "no_food", "unrecognized"]
FoodCategory = Literal["主食", "肉蛋海鲜", "蔬菜", "水果", "豆制品", "乳制品", "饮品", "甜品零食", "其他"]
Estimate = Annotated[Decimal, Field(ge=0, le=10000, decimal_places=2, max_digits=7, allow_inf_nan=False)]
WarningText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ESTIMATE_FIELDS = ("weight_g", "calories_kcal", "protein_g", "carbohydrates_g", "fat_g")


class AiFood(Input):
    food_name: Food
    category: FoodCategory | None
    weight_g: Estimate | None
    calories_kcal: Estimate | None
    protein_g: Estimate | None
    carbohydrates_g: Estimate | None
    fat_g: Estimate | None
    uncertainty: WarningText | None

    @field_validator(*ESTIMATE_FIELDS, mode="before")
    @classmethod
    def numeric_only(cls, value):
        if value is not None and type(value) not in (Decimal, float, int):
            raise ValueError("Use a JSON number or null")
        return value

    @field_serializer(*ESTIMATE_FIELDS, when_used="json")
    def json_number(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class Recognition(Input):
    schema_version: Literal["1"]
    status: RecognitionStatus
    foods: Annotated[list[AiFood], Field(max_length=15)]
    warnings: Annotated[list[WarningText], Field(max_length=6)]

    @model_validator(mode="after")
    def check_status(self):
        if bool(self.foods) != (self.status == "recognized"):
            raise ValueError("Food candidates must match the recognition status")
        return self

    def normalize_estimates(self):
        inconsistent = False
        for food in self.foods:
            macros = [food.protein_g, food.carbohydrates_g, food.fat_g]
            grams = sum(value for value in macros if value is not None)
            mass, energy = food.weight_g, food.calories_kcal
            invalid_mass = mass is not None and (mass == 0 or grams > mass + 2)
            if invalid_mass:
                food.weight_g = None
                inconsistent = True
            if energy is None:
                continue
            below_macros = energy + max(20, energy * Decimal("0.25")) < (
                (food.protein_g or 0) * 4 + (food.carbohydrates_g or 0) * 4 + (food.fat_g or 0) * 9
            )
            over_mass = mass is not None and energy > mass * 9 + 20
            if below_macros or over_mass:
                food.calories_kcal = None
                inconsistent = True
        if inconsistent:
            self.warnings = [*self.warnings[:5], "部分份量或营养估算存在矛盾，相关数值已留空。"]
        return self


class Candidate(AiFood):
    id: UUID


class RecognitionView(Recognition):
    foods: Annotated[list[Candidate], Field(max_length=15)]


class JobCreate(Input):
    media_ids: Annotated[list[UUID], Field(min_length=1, max_length=5)]
    consent_version: Annotated[str, StringConstraints(min_length=1, max_length=24)]
    form_meal_id: UUID | None = None

    @field_validator("media_ids")
    @classmethod
    def distinct_photos(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Each photo can appear only once")
        return values


class JobRetry(Input):
    consent_version: Annotated[str, StringConstraints(min_length=1, max_length=24)]
    accept_unknown_charge: StrictBool = False


class JobView(Input):
    id: UUID
    status: AiStatus
    simulated: bool
    result: RecognitionView | None
    error_code: str | None
    can_retry: bool
    attempt_count: int
    created_at: datetime
    expires_at: datetime
    media_ids: list[UUID]
    form_meal_id: UUID | None
    worker_online: bool


class AiCapabilities(Input):
    available: bool
    simulated: bool
    max_images: int
    consent_version: str
    privacy_url: str | None
    worker_online: bool


class UsageView(Input):
    used: int
    limit: int
    available: bool
    resets_at: datetime
    exhausted_reason: str | None
