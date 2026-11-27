import json
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.diary_schemas import CalendarDay, CalendarView, DailyView, ItemView, MealInput, MealPage, MealView, MediaView, NutrientSources, NutrientSummary
from app.models.diary import Meal, MealItem, MealMedia, MealRequest, MediaAsset
from app.models.stickers import MediaDerivative
from app.services.catalog import sync_item
from app.services.meal_sources import estimate_digest, item_values, verify_candidate
from app.services.storage import MEDIA_MISSING, lock_owner

NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrates_g", "fat_g")
MEAL_MISSING = "用餐记录不存在或不可访问。"


def meal_query(owner: str):
    return select(Meal).where(Meal.user_id == owner).options(
        selectinload(Meal.items), selectinload(Meal.attachments).joinedload(MealMedia.asset),
    ).execution_options(populate_existing=True)


def serialize(meal: Meal) -> MealView:
    return MealView(
        id=meal.id, meal_type=meal.meal_type, local_date=meal.local_date, eaten_at=meal.eaten_at,
        local_time=meal.eaten_at.astimezone(ZoneInfo(meal.timezone)).time(), timezone=meal.timezone,
        note=meal.note, version=meal.version, created_at=meal.created_at, updated_at=meal.updated_at,
        items=[ItemView.model_validate(item) for item in meal.items],
        media=[MediaView.model_validate(link.asset) for link in meal.attachments],
    )


def owned(db: Session, owner: str, identifier: str) -> Meal:
    meal = db.scalar(meal_query(owner).where(Meal.id == identifier))
    if meal is None:
        raise ApiError(404, "meal_not_found", MEAL_MISSING)
    return meal


def list_meals(db: Session, owner: str, start, end, meal_type, page: int, limit: int) -> MealPage:
    conditions = [Meal.user_id == owner]
    if start:
        conditions.append(Meal.local_date >= start)
    if end:
        conditions.append(Meal.local_date <= end)
    if meal_type:
        conditions.append(Meal.meal_type == meal_type)
    total = db.scalar(select(func.count()).select_from(Meal).where(*conditions))
    rows = db.scalars(meal_query(owner).where(*conditions)
                      .order_by(Meal.local_date.desc(), Meal.eaten_at.desc(), Meal.id.desc())
                      .offset((page - 1) * limit).limit(limit)).all()
    return MealPage(items=[serialize(row) for row in rows], page=page, limit=limit, total=total)


def payload(data: MealInput):
    return dict(meal_type=data.meal_type, local_date=data.local_date, eaten_at=data.eaten_at,
                timezone=data.timezone, note=data.note)


def update_items(db: Session, settings: Settings, owner: str, identifier: str, data: MealInput):
    previous = {row.id: row for row in db.scalars(select(MealItem).where(
        MealItem.meal_id == identifier,
    ).order_by(MealItem.sort_order))}
    explicit = [str(item.id) for item in data.items if item.id]
    if not set(explicit).issubset(previous):
        raise ApiError(404, "meal_item_not_found", "食物明细不存在或不可访问。")
    if len(explicit) != len(set(explicit)):
        raise ApiError(422, "meal_item_duplicate", "同一食物明细只能提交一次。")
    kept, candidates = set(), set()
    media_ids = {str(media) for media in data.media_ids}
    ordered = []
    for item in data.items:
        values = item_values(item)
        row = previous[str(item.id)] if item.id else None
        if not row and not item.ai_reference:
            # Phase 3 clients did not send IDs. Preserve exact matches without guessing at changed foods.
            row = next((old for old in previous.values() if old.id not in explicit and old.id not in kept
                        and all(getattr(old, name) == value for name, value in values.items())), None)
        if row:
            kept.add(row.id)
            if item.ai_reference:
                raise ApiError(422, "meal_item_reference", "已有食物明细的识别来源不能更换。")
            lineage = {}
        else:
            lineage = verify_candidate(db, settings, owner, identifier, media_ids, item.ai_reference) if item.ai_reference else {}
            row = MealItem(id=str(uuid4()), meal_id=identifier, source="manual", **lineage)
        if row.ai_candidate_id:
            if row.ai_candidate_id in candidates:
                raise ApiError(422, "ai_candidate_duplicate", "同一识别候选只能保存一次。")
            candidates.add(row.ai_candidate_id)
        ordered.append((row, values))
    for old in previous.values():
        if old.id in kept:
            old.sort_order = -old.sort_order - 1
        else:
            db.delete(old)
    db.flush()  # Free the nonnegative positions before reordering under the unique constraint.
    for order, (row, values) in enumerate(ordered):
        for name, value in values.items():
            setattr(row, name, value)
        row.sort_order = order
        if row.ai_original_digest:
            row.source = "ai" if estimate_digest(values) == row.ai_original_digest else "ai_edited"
        db.add(row)
    db.flush()
    for row, _ in ordered:
        sync_item(db, owner, row.id, row.food_name, row.category)


def replace_details(db: Session, settings: Settings, owner: str, identifier: str, data: MealInput):
    previous = db.scalars(select(MealMedia.media_id).where(MealMedia.meal_id == identifier)).all()
    selected = [str(media) for media in data.media_ids]
    if selected:
        valid = set(db.scalars(select(MediaAsset.id).where(MediaAsset.user_id == owner, MediaAsset.id.in_(selected))))
        if valid != set(selected):
            raise ApiError(404, "media_not_found", MEDIA_MISSING)
    update_items(db, settings, owner, identifier, data)
    db.execute(delete(MealMedia).where(MealMedia.meal_id == identifier))
    db.add_all([
        MealMedia(user_id=owner, meal_id=identifier, media_id=asset, sort_order=index)
        for index, asset in enumerate(selected)
    ])
    db.flush()
    sync_media(db, owner, set(previous) | set(selected))


def sync_media(db: Session, owner: str, media_ids: set[str]):
    if not media_ids:
        return
    referenced_ids = set(db.scalars(select(MealMedia.media_id).where(
        MealMedia.user_id == owner, MealMedia.media_id.in_(media_ids),
    ).distinct()))
    for status, identifiers in (("attached", referenced_ids), ("draft", media_ids - referenced_ids)):
        if identifiers:
            db.execute(update(MediaAsset).where(MediaAsset.user_id == owner, MediaAsset.id.in_(identifiers),
                                                MediaAsset.status != status)
                       .values(status=status, updated_at=utcnow()))


def create(db: Session, settings: Settings, owner: str, key: str, data: MealInput) -> tuple[MealView, bool]:
    serialized = data.model_dump()
    for item in serialized["items"]:
        for name in ("id", "ai_reference"):
            if item[name] is None:
                del item[name]  # Keep phase 3 request fingerprints valid.
    body = json.dumps(serialized, sort_keys=True, separators=(",", ":"),
                      default=lambda value: str(value.normalize()) if isinstance(value, Decimal) else str(value))
    digest = sha256(body.encode()).hexdigest()
    lock_owner(db, owner)
    previous = db.get(MealRequest, (owner, key))
    if previous:
        if previous.fingerprint != digest:
            raise ApiError(409, "idempotency_conflict", "同一保存标识不能用于不同内容。")
        if not previous.meal_id:
            raise ApiError(409, "idempotency_deleted", "这次提交对应的记录已删除。")
        return serialize(owned(db, owner, previous.meal_id)), True
    identifier = str(uuid4())
    db.add(Meal(id=identifier, user_id=owner, **payload(data)))
    db.flush()
    replace_details(db, settings, owner, identifier, data)
    db.add(MealRequest(user_id=owner, key=key, fingerprint=digest, meal_id=identifier))
    result = serialize(owned(db, owner, identifier))
    db.commit()
    return result, False


def version_conflict():
    return ApiError(409, "meal_version_conflict", "这条记录已在其他位置更新，请重新加载后再编辑。")


def edit(db: Session, settings: Settings, owner: str, identifier: str, data):
    lock_owner(db, owner)
    result = db.execute(update(Meal).where(Meal.id == identifier, Meal.user_id == owner, Meal.version == data.version)
                        .values(**payload(data), version=Meal.version + 1, updated_at=utcnow()))
    if result.rowcount != 1:
        owned(db, owner, identifier)
        raise version_conflict()
    replace_details(db, settings, owner, identifier, data)
    result = serialize(owned(db, owner, identifier))
    db.commit()
    return result


def remove(db: Session, owner: str, identifier: str, version: int | None):
    lock_owner(db, owner)
    meal = owned(db, owner, identifier)
    if version is not None and version != meal.version:
        raise version_conflict()
    media_ids = {item.media_id for item in meal.attachments}
    db.execute(delete(Meal).where(Meal.id == identifier, Meal.user_id == owner))
    sync_media(db, owner, media_ids)
    db.commit()


def calendar(db: Session, owner: str, month: str) -> CalendarView:
    try:
        first = date.fromisoformat(month + "-01")
        following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    except (ValueError, OverflowError):
        raise ApiError(422, "invalid_month", "请输入有效月份。") from None
    dates = [Meal.user_id == owner, Meal.local_date >= first, Meal.local_date < following]
    ranking = select(
        Meal.local_date.label("day"), MealMedia.media_id.label("image"),
        func.row_number().over(partition_by=Meal.local_date,
                              order_by=(MediaDerivative.id.is_not(None).desc(), Meal.eaten_at.desc(), Meal.id.desc(),
                                        MealMedia.sort_order)).label("position"),
    ).join(MealMedia, MealMedia.meal_id == Meal.id).outerjoin(
        MediaDerivative, (MediaDerivative.source_media_id == MealMedia.media_id) & (MediaDerivative.user_id == owner),
    ).where(*dates).subquery()
    counts = db.execute(select(Meal.local_date, func.count(Meal.id), ranking.c.image)
                        .outerjoin(ranking, (ranking.c.day == Meal.local_date) & (ranking.c.position == 1))
                        .where(*dates).group_by(Meal.local_date, ranking.c.image).order_by(Meal.local_date)).all()
    return CalendarView(month=month, days=[
        CalendarDay(date=day, meal_count=count, representative_media_id=image) for day, count, image in counts
    ])


def daily(db: Session, owner: str, day: date) -> DailyView:
    terms = []
    for name in NUTRIENTS:
        column = getattr(MealItem, name)
        terms.extend((func.sum(column), func.count(column),
                      func.count(column).filter(MealItem.source == "ai"),
                      func.count(column).filter(MealItem.source == "ai_edited"),
                      func.count(column).filter(MealItem.ai_provider == "fake")))
    totals = db.execute(select(func.count(MealItem.id), *terms).join(Meal)
                        .where(Meal.user_id == owner, Meal.local_date == day)).one()
    count = totals[0]
    nutrition = {}
    nutrition_sources = {}
    for index, name in enumerate(NUTRIENTS):
        offset = 1 + index * 5
        value, known, estimated, edited, simulated = totals[offset:offset + 5]
        nutrition[name] = NutrientSummary(value=value, known_items=known, complete=count > 0 and known == count)
        nutrition_sources[name] = NutrientSources(estimated=estimated, edited=edited, simulated=simulated)
    meals = db.scalar(select(func.count()).select_from(Meal).where(Meal.user_id == owner, Meal.local_date == day))
    return DailyView(date=day, meals=meals, items=count, nutrition=nutrition, nutrition_sources=nutrition_sources)
