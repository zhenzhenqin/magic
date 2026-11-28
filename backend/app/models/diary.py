from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow

class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        CheckConstraint("meal_type IN ('breakfast','lunch','dinner','snack')", name="ck_meals_type"),
        Index("ix_meals_owner_date_time", "user_id", "local_date", "eaten_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    meal_type: Mapped[str] = mapped_column(String(12))
    eaten_at: Mapped[datetime] = mapped_column(UTCDateTime())
    local_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    items: Mapped[list["MealItem"]] = relationship(order_by="MealItem.sort_order", cascade="all, delete-orphan")
    attachments: Mapped[list["MealMedia"]] = relationship(order_by="MealMedia.sort_order", viewonly=True)


class MealItem(Base):
    __tablename__ = "meal_items"
    __table_args__ = (UniqueConstraint("meal_id", "sort_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meal_id: Mapped[str] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"))
    food_name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(40))
    weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    calories_kcal: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    carbohydrates_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    note: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int]
    source: Mapped[str] = mapped_column(String(12), default="manual")
    ai_job_id: Mapped[str | None] = mapped_column(String(36))
    ai_candidate_id: Mapped[str | None] = mapped_column(String(36))
    ai_provider: Mapped[str | None] = mapped_column(String(16))
    ai_model: Mapped[str | None] = mapped_column(String(100))
    ai_prompt_version: Mapped[str | None] = mapped_column(String(24))
    ai_original_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        CheckConstraint("status IN ('draft','attached')", name="ck_media_status"),
        Index("ix_media_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    original_key: Mapped[str] = mapped_column(String(96), unique=True)
    thumbnail_key: Mapped[str] = mapped_column(String(96), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int]
    thumbnail_size_bytes: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class MealMedia(Base):
    __tablename__ = "meal_media"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "meal_id"], ["meals.user_id", "meals.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["user_id", "media_id"], ["media_assets.user_id", "media_assets.id"]),
        UniqueConstraint("meal_id", "sort_order"),
        Index("ix_meal_media_owner_asset", "user_id", "media_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36))
    meal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    media_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sort_order: Mapped[int]
    use_original: Mapped[bool] = mapped_column(server_default=false())
    asset: Mapped[MediaAsset] = relationship(viewonly=True)


class MealRequest(Base):
    __tablename__ = "meal_requests"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    meal_id: Mapped[str | None] = mapped_column(ForeignKey("meals.id", ondelete="SET NULL"), index=True)
