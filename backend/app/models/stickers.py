from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class StickerJob(Base):
    __tablename__ = "sticker_jobs"
    __table_args__ = (
        ForeignKeyConstraint(("user_id", "source_media_id"), ("media_assets.user_id", "media_assets.id"), ondelete="CASCADE"),
        UniqueConstraint("source_media_id"),
        CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')", name="ck_sticker_job_status"),
        Index("ix_sticker_jobs_queue", "status", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    source_media_id: Mapped[str] = mapped_column(String(36))
    source_digest: Mapped[str] = mapped_column(String(64))
    recipe: Mapped[str] = mapped_column(String(64))
    crop: Mapped[list[float] | None] = mapped_column(JSON(none_as_null=True))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    claim: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(32))
    timings: Mapped[dict[str, int] | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class MediaDerivative(Base):
    __tablename__ = "media_derivatives"
    __table_args__ = (
        ForeignKeyConstraint(("user_id", "source_media_id"), ("media_assets.user_id", "media_assets.id"), ondelete="CASCADE"),
        UniqueConstraint("source_media_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    source_media_id: Mapped[str] = mapped_column(String(36))
    source_digest: Mapped[str] = mapped_column(String(64))
    recipe: Mapped[str] = mapped_column(String(64))
    derivative_type: Mapped[str] = mapped_column(String(12), default="sticker")
    storage_key: Mapped[str] = mapped_column(String(96), unique=True)
    cutout_key: Mapped[str] = mapped_column(String(96), unique=True)
    thumbnail_key: Mapped[str] = mapped_column(String(96), unique=True)
    content_type: Mapped[str] = mapped_column(String(32), default="image/webp")
    width: Mapped[int]
    height: Mapped[int]
    size_bytes: Mapped[int]
    model_name: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(64))
    processing_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(12), default="ready")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class StickerRuntime(Base):
    __tablename__ = "sticker_runtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    heartbeat: Mapped[datetime] = mapped_column(UTCDateTime())
