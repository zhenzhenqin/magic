from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response

from app.core.exceptions import ApiError, ProblemResponse
from app.dependencies import CurrentUser, Database
from app.diary_schemas import CalendarView, DailyView, MealEdit, MealInput, MealPage, MealType, MealView
from app.services import diary

router = APIRouter(tags=["个人手账"], responses={401: {"model": ProblemResponse}, 404: {"model": ProblemResponse}})
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[a-z0-9_-]{8,128}$")]


@router.post("/meals", status_code=201, responses={200: {"model": MealView}, 409: {"model": ProblemResponse}})
def create(request: Request, data: MealInput, response: Response, user: CurrentUser, db: Database, key: IdempotencyKey) -> MealView:
    saved, replay = diary.create(db, request.app.state.settings, user.id, key, data)
    if replay:
        response.status_code = 200
    return saved


@router.get("/meals")
def list_meals(
    user: CurrentUser, db: Database, date_filter: Annotated[date | None, Query(alias="date")] = None,
    start: date | None = None, end: date | None = None, meal_type: MealType | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1, limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> MealPage:
    if (date_filter and (start or end)) or (start and end and end < start):
        raise ApiError(422, "invalid_date_range", "日期条件无效。")
    return diary.list_meals(db, user.id, date_filter or start, date_filter or end, meal_type, page, limit)


@router.get("/meals/{meal_id}")
def detail(user: CurrentUser, db: Database, meal_id: UUID) -> MealView:
    return diary.serialize(diary.owned(db, user.id, str(meal_id)))


@router.patch("/meals/{meal_id}", responses={409: {"model": ProblemResponse}})
def edit(request: Request, user: CurrentUser, db: Database, meal_id: UUID, data: MealEdit) -> MealView:
    return diary.edit(db, request.app.state.settings, user.id, str(meal_id), data)


@router.delete("/meals/{meal_id}", status_code=204, responses={409: {"model": ProblemResponse}})
def remove(user: CurrentUser, db: Database, meal_id: UUID, version: Annotated[int | None, Query(ge=1)] = None):
    diary.remove(db, user.id, str(meal_id), version)
    return Response(status_code=204)


@router.get("/calendar")
def calendar(user: CurrentUser, db: Database, month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]) -> CalendarView:
    return diary.calendar(db, user.id, month)


@router.get("/statistics/daily")
def daily(user: CurrentUser, db: Database, date: date) -> DailyView:
    return diary.daily(db, user.id, date)
