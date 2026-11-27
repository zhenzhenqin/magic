from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import StringConstraints

from app.core.exceptions import ApiError
from app.dependencies import CurrentUser, Database
from app.services import friends, sharing
from app.sharing_schemas import (
    Friend, FriendList, GrantEdit, Person, PublicId, RequestCreate, RequestView, ShareFlags,
    SharedCalendar, SharedDaily, SharedFood, SharedFoods, SharedHistory, SharedMeal, SharedMeals,
)

router = APIRouter(prefix="/friends", tags=["饭搭子及授权共享"])
Page = Annotated[int, Query(ge=1, le=10000)]
Limit = Annotated[int, Query(ge=1, le=50)]
FoodId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]


@router.get("")
def listing(user: CurrentUser, db: Database) -> FriendList:
    return friends.listing(db, user)


@router.get("/lookup")
def lookup(request: Request, user: CurrentUser, db: Database, public_id: PublicId) -> Person:
    request.app.state.rate_limiter.check("friend_lookup", user.id, request.app.state.settings.friend_lookup_attempts)
    other = friends.peer(db, public_id)
    if other.id == user.id:
        raise ApiError(422, "friend_self", "这是你自己的公开 ID。")
    return friends.person(other)


@router.get("/requests")
def requests(user: CurrentUser, db: Database) -> list[RequestView]:
    return friends.requests(db, user.id)


@router.post("/requests", status_code=202)
def send(request: Request, user: CurrentUser, db: Database, data: RequestCreate) -> RequestView:
    request.app.state.rate_limiter.check("friend_send", user.id, request.app.state.settings.friend_request_attempts)
    return friends.send(db, user.id, data.public_id)


@router.post("/requests/{identifier}/{action}")
def respond(user: CurrentUser, db: Database, identifier: UUID, action: Literal["accept", "reject", "cancel"]) -> RequestView:
    return friends.respond(db, user.id, str(identifier), {"accept": "accepted", "reject": "rejected", "cancel": "cancelled"}[action])


@router.delete("/{peer_id}", status_code=204)
def remove(user: CurrentUser, db: Database, peer_id: PublicId, relationship_id: UUID):
    friends.remove(db, user.id, peer_id, str(relationship_id))
    return Response(status_code=204)


@router.get("/{peer_id}/sharing")
def grants(user: CurrentUser, db: Database, peer_id: PublicId) -> Friend:
    return friends.sharing(db, user.id, peer_id)


@router.put("/{peer_id}/sharing")
def update(user: CurrentUser, db: Database, peer_id: PublicId, data: GrantEdit) -> Friend:
    return friends.update_grant(db, user.id, peer_id, str(data.relationship_id), data.version, data.permissions, data.history_scope)


@router.delete("/{peer_id}/sharing")
def stop(user: CurrentUser, db: Database, peer_id: PublicId, relationship_id: UUID, version: Annotated[int, Query(ge=0)]) -> Friend:
    return friends.update_grant(db, user.id, peer_id, str(relationship_id), version, ShareFlags())


@router.get("/{peer_id}/meals", response_model_exclude_unset=True)
def list_meals(user: CurrentUser, db: Database, peer_id: PublicId, date: date, page: Page = 1, limit: Limit = 24) -> SharedMeals:
    return sharing.meals(db, sharing.SharingPolicy.open(db, user.id, peer_id), date, page, limit)


@router.get("/{peer_id}/meals/{identifier}", response_model_exclude_unset=True)
def meal(user: CurrentUser, db: Database, peer_id: PublicId, identifier: UUID) -> SharedMeal:
    return sharing.meal(db, sharing.SharingPolicy.open(db, user.id, peer_id), str(identifier))


@router.get("/{peer_id}/calendar", response_model_exclude_unset=True)
def calendar(user: CurrentUser, db: Database, peer_id: PublicId,
             month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]) -> SharedCalendar:
    return sharing.calendar(db, sharing.SharingPolicy.open(db, user.id, peer_id), month)


@router.get("/{peer_id}/statistics/daily", response_model_exclude_unset=True)
def daily(user: CurrentUser, db: Database, peer_id: PublicId, date: date) -> SharedDaily:
    return sharing.daily(db, sharing.SharingPolicy.open(db, user.id, peer_id), date)


@router.get("/{peer_id}/catalog", response_model_exclude_unset=True)
def catalog(user: CurrentUser, db: Database, peer_id: PublicId, page: Page = 1, limit: Limit = 24,
            search: Annotated[str, Query(max_length=80)] = "", category: Annotated[str, Query(max_length=40)] = "") -> SharedFoods:
    return sharing.foods(db, sharing.SharingPolicy.open(db, user.id, peer_id), search, category, page, limit)


@router.get("/{peer_id}/catalog/{identifier}", response_model_exclude_unset=True)
def food(user: CurrentUser, db: Database, peer_id: PublicId, identifier: FoodId) -> SharedFood:
    return sharing.food(db, sharing.SharingPolicy.open(db, user.id, peer_id), identifier)


@router.get("/{peer_id}/catalog/{identifier}/history")
def history(user: CurrentUser, db: Database, peer_id: PublicId, identifier: FoodId,
            page: Page = 1, limit: Limit = 12) -> SharedHistory:
    return sharing.food_history(db, sharing.SharingPolicy.open(db, user.id, peer_id), identifier, page, limit)


@router.get("/{peer_id}/media/{media_id}", response_class=FileResponse)
@router.get("/{peer_id}/media/{media_id}/{variant:path}", response_class=FileResponse)
def media(request: Request, user: CurrentUser, db: Database, peer_id: PublicId, media_id: UUID,
          variant: str = "photo",
          meal_id: UUID | None = None, catalog_id: FoodId | None = None):
    if bool(meal_id) == bool(catalog_id) or variant not in ("photo", "thumbnail", "sticker", "sticker/thumbnail"):
        raise friends.hidden()
    policy = sharing.SharingPolicy.open(db, user.id, peer_id)
    key = sharing.media_key(db, policy, str(media_id), variant, str(meal_id) if meal_id else None, catalog_id)
    try:
        path = request.app.state.storage.path(key)
    except ValueError:
        raise friends.hidden() from None
    if not path.is_file():
        raise friends.hidden()
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
