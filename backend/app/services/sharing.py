from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select

from app.core.database import utcnow
from app.food_names import ALIASES, canonical
from app.models.diary import Meal, MealItem, MealMedia, MediaAsset
from app.models.stickers import MediaDerivative
from app.services.friends import FLAGS, direction, hidden, relation
from app.services.storage import used_by_ai

NUTRIENTS = ("weight_g", "protein_g", "carbohydrates_g", "fat_g")
ITEM_FIELDS = {
    "names": ("food_name", "category"),
    "calories": ("calories_kcal",),
    "nutrition": NUTRIENTS,
    "notes": ("note",),
}


@dataclass(frozen=True)
class SharingPolicy:
    owner: str
    flags: int
    start: date | None

    @classmethod
    def open(cls, db, viewer, public_id):
        # sqlite3 legacy mode does not start a transaction for a SELECT. Use a read
        # snapshot for both the grant and the scoped data, even on the legacy driver.
        connection = db.connection()
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
        relationship, owner = relation(db, viewer, public_id)
        grant = direction(db, relationship.id, owner.id, viewer)
        return cls(owner.id, grant.flags if grant else 0, grant.history_start if grant else None)

    def allows(self, scope):
        return bool(self.flags & FLAGS[scope])

    def require(self, *scopes):
        if not all(self.allows(scope) for scope in scopes):
            raise hidden()

    def contains(self, day):
        return self.start is None or day >= self.start

    def conditions(self):
        return (Meal.user_id == self.owner,) if self.start is None else (
            Meal.user_id == self.owner, Meal.local_date >= self.start,
        )

    def kinds(self):
        return [kind for permission, kind in (("stickers", "sticker"), ("photos", "photo")) if self.allows(permission)]

    def scope_media(self, query):
        query = (query.join(MediaAsset, (MediaAsset.id == MealMedia.media_id) & (MediaAsset.user_id == MealMedia.user_id))
                 .where(MealMedia.user_id == self.owner, MediaAsset.status == "attached", ~used_by_ai(MediaAsset.id, utcnow())))
        return query if self.allows("photos") else query.where(MealMedia.use_original.is_(False))

    def food_rows(self):
        return (select(func.fooddiary_name(MealItem.food_name).label("name"), MealItem.food_name.label("label"),
                       MealItem.category, MealItem.id.label("item_id"), Meal.id.label("meal_id"),
                       Meal.local_date.label("day"), Meal.eaten_at.label("eaten"))
                .join(Meal, Meal.id == MealItem.meal_id).where(*self.conditions()).subquery())


def page(db, query, page_number, limit, order):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(*order).offset((page_number - 1) * limit).limit(limit)).all()
    return rows, total


def media_value(identifier, kinds, original=False):
    return dict(id=identifier, kinds=[kind for kind in kinds if kind != "sticker"] if original else kinds)


def meals_projection(db, policy, rows):
    ids = [meal.id for meal in rows]
    field_names = [field for scope, fields in ITEM_FIELDS.items() if policy.allows(scope) for field in fields]
    items, media = defaultdict(list), defaultdict(list)
    if ids and field_names:
        fields = [getattr(MealItem, field) for field in field_names]
        quantities = [field for field in ("calories_kcal", *NUTRIENTS) if field in field_names]
        for meal, source, *values in db.execute(select(MealItem.meal_id, MealItem.source, *fields)
                                              .where(MealItem.meal_id.in_(ids)).order_by(MealItem.meal_id, MealItem.sort_order)):
            visible = dict(zip(field_names, values, strict=True))
            if any(visible[field] is not None for field in quantities):
                visible["estimated"] = source in ("ai", "ai_edited")
            items[meal].append(visible)
    kinds = policy.kinds()
    if ids and kinds:
        query = policy.scope_media(select(MealMedia.meal_id, MealMedia.media_id, MealMedia.use_original)).where(MealMedia.meal_id.in_(ids))
        for meal, image, original in db.execute(query.order_by(MealMedia.meal_id, MealMedia.sort_order)):
            media[meal].append(media_value(image, kinds, original))
    result = []
    for meal in rows:
        local_time = meal.eaten_at.astimezone(ZoneInfo(meal.timezone)).strftime("%H:%M")
        data = dict(id=meal.id, local_date=meal.local_date, local_time=local_time, meal_type=meal.meal_type)
        if field_names:
            data["items"] = items[meal.id]
        if kinds:
            data["media"] = media[meal.id]
        if policy.allows("notes"):
            data["note"] = meal.note
        result.append(data)
    return result


def meals(db, policy, day, page_number, limit):
    policy.require("records")
    query = select(Meal).where(Meal.local_date == day, *policy.conditions())
    rows, total = page(db, query, page_number, limit, (Meal.eaten_at, Meal.id))
    return dict(items=meals_projection(db, policy, [row[0] for row in rows]), total=total, page=page_number, limit=limit)


def meal(db, policy, identifier):
    policy.require("records")
    row = db.scalar(select(Meal).where(Meal.id == identifier, *policy.conditions()))
    if row is None:
        raise hidden()
    return meals_projection(db, policy, [row])[0]


def sticker_cover_order(query, policy):
    if policy.allows("stickers"):
        return query.outerjoin(MediaDerivative, (MediaDerivative.source_media_id == MealMedia.media_id)
                               & (MediaDerivative.user_id == policy.owner) & (MediaDerivative.status == "ready")
                               & MealMedia.use_original.is_(False)), (
                                   MediaDerivative.id.is_not(None).desc(),
                               )
    return query, ()


def calendar(db, policy, month):
    policy.require("records")
    try:
        beginning = date.fromisoformat(month + "-01")
        following = (beginning.replace(day=28) + timedelta(days=4)).replace(day=1)
    except (ValueError, OverflowError):
        raise hidden() from None
    bounds = (*policy.conditions(), Meal.local_date >= beginning, Meal.local_date < following)
    counts = db.execute(select(Meal.local_date, func.count()).where(*bounds).group_by(Meal.local_date)
                        .order_by(Meal.local_date)).all()
    covers = {}
    kinds = policy.kinds()
    if counts and kinds:
        images = select(Meal.local_date, Meal.id.label("meal_id"), MealMedia.media_id, MealMedia.use_original).select_from(Meal).join(
            MealMedia, MealMedia.meal_id == Meal.id,
        ).where(*bounds)
        images = policy.scope_media(images)
        images, preference = sticker_cover_order(images, policy)
        ranked = images.add_columns(func.row_number().over(partition_by=Meal.local_date, order_by=(
            *preference, Meal.eaten_at.desc(), Meal.id, MealMedia.sort_order,
        )).label("rank")).subquery()
        covers = {day: dict(media=media_value(image, kinds, original), meal_id=meal_id) for day, meal_id, image, original in db.execute(
            select(ranked.c.local_date, ranked.c.meal_id, ranked.c.media_id, ranked.c.use_original).where(ranked.c.rank == 1),
        )}
    return dict(month=month, days=[dict(date=day, meals=count, **covers.get(day, {})) for day, count in counts])


def daily(db, policy, day):
    policy.require("records")
    bounds = (*policy.conditions(), Meal.local_date == day)
    result = dict(date=day, meals=db.scalar(select(func.count()).select_from(Meal).where(*bounds)))
    names = [field for flag, selected in (("calories", ("calories_kcal",)), ("nutrition", NUTRIENTS))
             if policy.allows(flag) for field in selected]
    if names:
        terms = []
        for name in names:
            column = getattr(MealItem, name)
            terms += [func.sum(column), func.count(column),
                      func.max(case((column.is_not(None) & MealItem.source.in_(("ai", "ai_edited")), 1), else_=0))]
        count, *values = db.execute(select(func.count(), *terms).select_from(MealItem).join(Meal).where(*bounds)).one()
        result["nutrition"] = {
            name: dict(value=value, known_items=known, complete=bool(count and known == count), estimated=bool(estimate))
            for name, value, known, estimate in zip(names, values[::3], values[1::3], values[2::3], strict=True)
        }
    return result


def food_groups(rows):
    return (select(rows.c.name, func.fooddiary_catalog_id(rows.c.name).label("id"),
                   func.min(rows.c.label).label("label"), func.min(rows.c.category).label("category"),
                   func.count(func.distinct(rows.c.meal_id)).label("occurrences"), func.count().label("items"),
                   func.min(rows.c.day).label("first_eaten"), func.max(rows.c.day).label("last_eaten"),
                   func.max(rows.c.eaten).label("recent")).group_by(rows.c.name).subquery())


def food_covers(db, policy, source, names, kinds):
    gallery = select(source.c.name, source.c.meal_id, source.c.eaten).where(
        source.c.name.in_(names),
    ).distinct().subquery()
    photos = select(gallery.c.name, MealMedia.media_id, MealMedia.use_original, (select(func.count()).select_from(MealItem).where(
        MealItem.meal_id == MealMedia.meal_id,
    ).correlate(MealMedia).scalar_subquery() > 1).label("whole")).select_from(gallery).join(
        MealMedia, MealMedia.meal_id == gallery.c.meal_id,
    )
    photos, preference = sticker_cover_order(policy.scope_media(photos), policy)
    rank = photos.add_columns(func.row_number().over(partition_by=gallery.c.name, order_by=(
        *preference, gallery.c.eaten.desc(), gallery.c.meal_id, MealMedia.sort_order,
    )).label("rank")).subquery()
    return {name: dict(cover=media_value(image, kinds, original), cover_whole_meal=whole) for name, image, original, whole in db.execute(
        select(rank.c.name, rank.c.media_id, rank.c.use_original, rank.c.whole).where(rank.c.rank == 1),
    )}


def foods_projection(db, policy, source, rows):
    if not rows:
        return []
    kinds = policy.kinds()
    covers = food_covers(db, policy, source, [row.name for row in rows], kinds) if kinds else {}
    return [dict(id=row.id, name=row.name if row.name in ALIASES.values() else row.label,
                 category=row.category, **covers.get(row.name, {}), **(
                     dict(occurrences=row.occurrences, items=row.items, first_eaten=row.first_eaten, last_eaten=row.last_eaten)
                     if policy.allows("history") else {}
                 )) for row in rows]


def foods(db, policy, search, category, page_number, limit):
    policy.require("catalog")
    result = dict(names_shared=policy.allows("names"), items=[], page=page_number, limit=limit)
    if not result["names_shared"]:
        return result
    source = policy.food_rows()
    groups = food_groups(source)
    query = select(groups)
    if search.strip():
        query = query.where(groups.c.name.contains(canonical(search), autoescape=True))
    if category:
        query = query.where(groups.c.category == category)
    rows, total = page(db, query, page_number, limit, (groups.c.recent.desc(), groups.c.id))
    result.update(items=foods_projection(db, policy, source, rows), total=total, categories=db.scalars(
        select(groups.c.category).where(groups.c.category.is_not(None)).distinct().order_by(groups.c.category),
    ).all())
    return result


def food(db, policy, identifier):
    policy.require("catalog", "names")
    source = policy.food_rows()
    groups = food_groups(source)
    row = db.execute(select(groups).where(groups.c.id == identifier)).first()
    if row is None:
        raise hidden()
    return foods_projection(db, policy, source, [row])[0]


def food_history(db, policy, identifier, page_number, limit):
    policy.require("catalog", "names", "history")
    source = policy.food_rows()
    related = select(source.c.meal_id).where(func.fooddiary_catalog_id(source.c.name) == identifier).distinct()
    query = select(Meal.id, Meal.local_date, Meal.meal_type).where(Meal.id.in_(related))
    rows, total = page(db, query, page_number, limit, (Meal.eaten_at.desc(), Meal.id))
    if not total:
        raise hidden()
    return dict(items=[dict(id=meal_id, local_date=day, meal_type=kind) for meal_id, day, kind in rows],
                total=total, page=page_number, limit=limit)


def media_key(db, policy, media_id, variant, meal_id=None, catalog_id=None):
    policy.require("photos" if variant in ("photo", "thumbnail") else "stickers")
    query = select(MediaAsset).select_from(Meal).join(MealMedia, MealMedia.meal_id == Meal.id).where(
        *policy.conditions(), MealMedia.media_id == media_id,
    )
    query = policy.scope_media(query)
    if variant not in ("photo", "thumbnail"):
        query = query.where(MealMedia.use_original.is_(False))
    if catalog_id:
        policy.require("catalog", "names")
        source = policy.food_rows()
        query = query.where(Meal.id.in_(select(source.c.meal_id).where(func.fooddiary_catalog_id(source.c.name) == catalog_id)))
    else:
        policy.require("records")
        query = query.where(Meal.id == meal_id)
    asset = db.scalar(query.limit(1))
    if asset is None:
        raise hidden()
    if variant in ("photo", "thumbnail"):
        return asset.original_key if variant == "photo" else asset.thumbnail_key
    derivative = db.scalar(select(MediaDerivative).where(MediaDerivative.user_id == policy.owner,
                                                         MediaDerivative.source_media_id == asset.id, MediaDerivative.status == "ready"))
    if derivative is None:
        raise hidden()
    return derivative.storage_key if variant == "sticker" else derivative.thumbnail_key
