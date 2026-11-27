from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class FoodCatalog(Base):
    __tablename__ = "food_catalog"
    __table_args__ = (UniqueConstraint("user_id", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    canonical_name: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(40))
    cover_media_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id", ondelete="SET NULL"))
    is_favorite: Mapped[bool] = mapped_column(default=False)
    category_custom: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CatalogName(Base):
    __tablename__ = "catalog_names"
    __table_args__ = (ForeignKeyConstraint(("user_id", "catalog_id"), ("food_catalog.user_id", "food_catalog.id"), ondelete="CASCADE"),)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    catalog_id: Mapped[str] = mapped_column(String(36), index=True)


class CatalogLink(Base):
    __tablename__ = "catalog_links"
    __table_args__ = (ForeignKeyConstraint(("user_id", "catalog_id"), ("food_catalog.user_id", "food_catalog.id"), ondelete="CASCADE"),)
    item_id: Mapped[str] = mapped_column(ForeignKey("meal_items.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    catalog_id: Mapped[str] = mapped_column(String(36), index=True)
