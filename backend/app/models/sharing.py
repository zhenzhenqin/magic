from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow


class FriendRequest(Base):
    __tablename__ = "friend_requests"
    __table_args__ = (
        UniqueConstraint("low_id", "high_id"),
        CheckConstraint("low_id < high_id", name="ck_friend_request_order"),
        CheckConstraint("(sender_id = low_id AND recipient_id = high_id) OR (sender_id = high_id AND recipient_id = low_id)",
                        name="ck_friend_request_members"),
        CheckConstraint("status IN ('pending','accepted','rejected','cancelled')", name="ck_friend_request_status"),
        Index("ix_friend_request_inbox", "recipient_id", "status", "created_at"),
        Index("ix_friend_request_outbox", "sender_id", "status", "created_at"),
        Index("ix_friend_request_created", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    low_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    high_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    sender_id: Mapped[str] = mapped_column(String(36))
    recipient_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("low_id", "high_id"),
        CheckConstraint("low_id < high_id", name="ck_friendship_order"),
        Index("ix_friendship_high_low", "high_id", "low_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    low_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    high_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SharePermission(Base):
    __tablename__ = "share_permissions"
    __table_args__ = (
        CheckConstraint("owner_id != viewer_id", name="ck_share_distinct_users"),
        CheckConstraint("flags >= 0 AND flags <= 511", name="ck_share_flag_range"),
        CheckConstraint("history_scope IN ('today','week','month','all')", name="ck_share_history_scope"),
        Index("ix_share_permission_direction", "viewer_id", "owner_id"),
    )
    friendship_id: Mapped[str] = mapped_column(ForeignKey("friendships.id", ondelete="CASCADE"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    viewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    flags: Mapped[int] = mapped_column(default=0)
    history_scope: Mapped[str] = mapped_column(String(8), default="today")
    history_start: Mapped[date | None] = mapped_column(Date)
    granted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    version: Mapped[int] = mapped_column(default=1)


class ShareAudit(Base):
    __tablename__ = "share_audit"
    __table_args__ = (
        Index("ix_share_audit_actor_time", "actor_id", "created_at"),
        Index("ix_share_audit_time", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    peer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class MediaWriteReservation(Base):
    __tablename__ = "media_write_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    size_bytes: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
