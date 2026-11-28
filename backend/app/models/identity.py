from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


class EmailChallenge(Base):
    __tablename__ = "email_challenges"
    __table_args__ = (
        Index("ix_email_challenges_mail_time", "mail_scope", "created_at"),
        Index("ix_email_challenges_ip_time", "ip_scope", "created_at"),
        Index("ix_email_challenges_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mail_scope: Mapped[str] = mapped_column(String(64))
    ip_scope: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(16))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    digest: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Invitation(Base):
    __tablename__ = "account_invitations"
    __table_args__ = (CheckConstraint("remaining >= 0", name="ck_account_invite_remaining"),)

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    remaining: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
