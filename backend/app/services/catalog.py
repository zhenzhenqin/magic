from datetime import date
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.food_names import ALIASES, canonical
from app.models.catalog import CatalogLink, CatalogName, FoodCatalog
from app.models.diary import Meal, MealItem, MealMedia
from app.models.stickers import MediaDerivative
from app.services.storage import lock_owner

def sync_item(db, user_id: str, item_id: str, food_name: str, category: str | None):
    key = canonical(food_name)
    alias = db.get(CatalogName, (user_id, key))
    if alias is None:
        identifier = str(uuid4())
        db.add(FoodCatalog(id=identifier, user_id=user_id, canonical_name=key,
                           display_name=key if key in ALIASES.values() else food_name, category=category))
        db.flush()
        alias = CatalogName(user_id=user_id, name=key, catalog_id=identifier)
        db.add(alias)
        db.flush()
    else:
        entry = db.get(FoodCatalog, alias.catalog_id)
        if entry and not entry.category_custom and entry.category != category:
            entry.category = category
    link = db.get(CatalogLink, item_id)
    if link:
        link.catalog_id = alias.catalog_id
    else:
        db.add(CatalogLink(item_id=item_id, user_id=user_id, catalog_id=alias.catalog_id))


def metrics(owner):
    return (select(CatalogLink.catalog_id.label("id"), func.count(func.distinct(Meal.id)).label("occasions"),
                   func.count().label("details"), func.min(Meal.local_date).label("first"),
                   func.max(Meal.local_date).label("last"), func.max(Meal.eaten_at).label("recent"))
            .join(MealItem, MealItem.id == CatalogLink.item_id)
            .join(Meal, (Meal.id == MealItem.meal_id) & (Meal.user_id == CatalogLink.user_id))
            .where(CatalogLink.user_id == owner).group_by(CatalogLink.catalog_id).subquery())


def cover_options(owner, identifier):
    meals = (select(MealItem.meal_id).join(CatalogLink, CatalogLink.item_id == MealItem.id)
             .where(CatalogLink.user_id == owner, CatalogLink.catalog_id == identifier))
    whole_meal = (select(func.count()).select_from(MealItem).where(MealItem.meal_id == MealMedia.meal_id)
                  .correlate(MealMedia).scalar_subquery() > 1)
    return (select(MealMedia.media_id, whole_meal.label("whole_meal"))
            .join(Meal, (Meal.id == MealMedia.meal_id) & (Meal.user_id == MealMedia.user_id))
            .outerjoin(MediaDerivative, (MediaDerivative.source_media_id == MealMedia.media_id)
                       & (MediaDerivative.user_id == MealMedia.user_id))
            .where(MealMedia.user_id == owner, MealMedia.meal_id.in_(meals))
            .order_by(MediaDerivative.id.is_not(None).desc(), Meal.eaten_at.desc(), MealMedia.sort_order, Meal.id))


def projection(db, owner, entry, occasions, details, first, last):
    choices = cover_options(owner, entry.id)
    picked = db.execute(choices.where(MealMedia.media_id == entry.cover_media_id).limit(1)).first() if entry.cover_media_id else None
    if picked is None:
        picked = db.execute(choices.limit(1)).first()
    return dict(id=entry.id, canonical_name=entry.canonical_name, display_name=entry.display_name,
                category=entry.category, cover_media_id=picked.media_id if picked else None,
                cover_whole_meal=bool(picked and picked.whole_meal), is_favorite=entry.is_favorite,
                first_eaten=first, last_eaten=last, occasions=occasions or 0, details=details or 0)


def row_query(owner):
    counts = metrics(owner)
    return (select(FoodCatalog, counts.c.occasions, counts.c.details, counts.c.first, counts.c.last)
            .outerjoin(counts, FoodCatalog.id == counts.c.id).where(FoodCatalog.user_id == owner)), counts


def list_catalog(db, owner, search, category, favorites, sort, page, limit):
    query, counts = row_query(owner)
    query = query.where(FoodCatalog.is_favorite.is_(True)) if favorites else query.where(counts.c.id.is_not(None))
    if search:
        query = query.where(FoodCatalog.display_name.contains(search, autoescape=True)
                            | FoodCatalog.canonical_name.contains(canonical(search), autoescape=True)
                            | FoodCatalog.id.in_(select(CatalogName.catalog_id).where(
                                CatalogName.user_id == owner, CatalogName.name.contains(canonical(search), autoescape=True))))
    if category:
        query = query.where(FoodCatalog.category == category)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    ordering = (counts.c.occasions.desc(), counts.c.recent.desc()) if sort == "occasions" else (counts.c.recent.desc(),)
    rows = db.execute(query.order_by(*ordering, FoodCatalog.id).offset((page - 1) * limit).limit(limit)).all()
    collected = db.scalar(select(func.count()).select_from(counts))
    categories = db.scalars(select(FoodCatalog.category).join(counts, FoodCatalog.id == counts.c.id)
                            .where(FoodCatalog.user_id == owner, FoodCatalog.category.is_not(None))
                            .distinct().order_by(FoodCatalog.category)).all()
    return dict(items=[projection(db, owner, *row) for row in rows], page=page, limit=limit,
                total=total, collected=collected, categories=categories)


def missing():
    return ApiError(404, "catalog_not_found", "这项收藏不存在或不可访问。")


def detail(db, owner, identifier):
    query, _ = row_query(owner)
    row = db.execute(query.where(FoodCatalog.id == identifier)).first()
    if row is None:
        raise missing()
    return projection(db, owner, *row)


def owned(db, owner, identifier):
    entry = db.scalar(select(FoodCatalog).where(FoodCatalog.id == identifier, FoodCatalog.user_id == owner))
    if entry is None:
        raise missing()
    return entry


def edit(db, owner, identifier, changes):
    lock_owner(db, owner)
    entry = owned(db, owner, identifier)
    if changes.get("cover_media_id"):
        cover = str(changes["cover_media_id"])
        if db.execute(cover_options(owner, identifier).where(MealMedia.media_id == cover).limit(1)).first() is None:
            raise ApiError(404, "media_not_found", "图片不属于这项美食的有效记录。")
        changes["cover_media_id"] = cover
    if "category" in changes:
        entry.category_custom = True
    for key, value in changes.items():
        setattr(entry, key, value)
    db.flush()
    result = detail(db, owner, identifier)
    db.commit()
    return result


def history(db, owner, identifier, page, limit):
    owned(db, owner, identifier)
    meal_ids = (select(MealItem.meal_id).join(CatalogLink, CatalogLink.item_id == MealItem.id)
                .where(CatalogLink.user_id == owner, CatalogLink.catalog_id == identifier).distinct())
    rows = select(Meal).where(Meal.user_id == owner, Meal.id.in_(meal_ids))
    total = db.scalar(select(func.count()).select_from(rows.subquery()))
    meals = db.scalars(rows.order_by(Meal.eaten_at.desc(), Meal.id).offset((page - 1) * limit).limit(limit)).all()
    result = []
    for meal in meals:
        images = db.scalars(select(MealMedia.media_id).where(MealMedia.user_id == owner, MealMedia.meal_id == meal.id)
                            .order_by(MealMedia.sort_order)).all()
        result.append(dict(meal_id=meal.id, local_date=meal.local_date, meal_type=meal.meal_type,
                           eaten_at=meal.eaten_at, media_ids=images))
    return dict(items=result, total=total, page=page, limit=limit)


def merge(db, owner, source_id, target_id):
    if source_id == target_id:
        raise ApiError(422, "catalog_same_entry", "请选择另一项美食。")
    lock_owner(db, owner)
    source, target = owned(db, owner, source_id), owned(db, owner, target_id)
    for model in (CatalogLink, CatalogName):
        db.execute(update(model).where(model.user_id == owner, model.catalog_id == source.id).values(catalog_id=target.id))
    target.is_favorite = target.is_favorite or source.is_favorite
    target.cover_media_id = target.cover_media_id or source.cover_media_id
    target.updated_at = utcnow()
    db.delete(source)
    db.flush()
    result = detail(db, owner, target_id)
    db.commit()
    return result
