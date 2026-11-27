from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class AiJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "id"),
        UniqueConstraint("user_id", "request_key"),
        CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')", name="ck_ai_job_status"),
        Index("ix_ai_jobs_queue", "status", "available_at"),
        Index("ix_ai_jobs_owner_status", "user_id", "status"),
        Index("ix_ai_jobs_completed", "completed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    request_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    job_type: Mapped[str] = mapped_column(String(24), default="food_recognition")
    status: Mapped[str] = mapped_column(String(12), default="pending")
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(24))
    consent_version: Mapped[str] = mapped_column(String(24))
    processing_fingerprint: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int]
    result_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    adopted_meal_id: Mapped[str | None] = mapped_column(String(36))
    form_meal_id: Mapped[str | None] = mapped_column(String(36))
    media_snapshot: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True))
    available_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claim_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class AiJobMedia(Base):
    __tablename__ = "ai_job_media"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "job_id"], ["ai_jobs.user_id", "ai_jobs.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["user_id", "media_id"], ["media_assets.user_id", "media_assets.id"], ondelete="CASCADE"),
        UniqueConstraint("job_id", "sort_order"),
        Index("ix_ai_job_media_owner_asset", "user_id", "media_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    media_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sort_order: Mapped[int]


class AiUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_provider_time", "provider", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL",
                                                        name="fk_ai_usage_logs_user"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("ai_jobs.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(40))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    elapsed_ms: Mapped[int | None]
    upstream_request_id: Mapped[str | None] = mapped_column(String(128))
    usage_known: Mapped[bool] = mapped_column(default=False)
    hold_until: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AiRetryRequest(Base):
    __tablename__ = "ai_retry_requests"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "job_id"], ["ai_jobs.user_id", "ai_jobs.id"], ondelete="CASCADE"),
        Index("ix_ai_retry_owner_job", "job_id", "user_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class AiCallBudget(Base):
    __tablename__ = "ai_call_budgets"
    __table_args__ = (CheckConstraint("spent >= 0", name="ck_ai_call_budget_nonnegative"),)

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    spent: Mapped[int]


class AiWorkerHeartbeat(Base):
    __tablename__ = "ai_worker_heartbeats"

    configuration: Mapped[str] = mapped_column(String(64), primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime())
