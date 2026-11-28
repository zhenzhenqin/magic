"""Add optional verified email, invitation, and personal credential references."""

from alembic import op
import sqlalchemy as sa


revision = "0011_personal_identity"
down_revision = "0010_sticker_timings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email", sa.String(254)))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime()))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.add_column("auth_sessions", sa.Column("device", sa.String(32)))
    op.add_column("user_settings", sa.Column("ai_daily_limit", sa.Integer()))
    op.add_column("user_settings", sa.Column("ai_intro_dismissed", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("ai_jobs", sa.Column("credential_ref", sa.String(36)))
    op.add_column("ai_jobs", sa.Column("credential_session_id", sa.String(36)))
    op.add_column("ai_usage_logs", sa.Column("credential_ref", sa.String(36)))
    op.create_table(
        "email_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mail_scope", sa.String(64), nullable=False),
        sa.Column("ip_scope", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.Column("delivered_at", sa.DateTime()),
    )
    op.create_index("ix_email_challenges_mail_time", "email_challenges", ["mail_scope", "created_at"])
    op.create_index("ix_email_challenges_ip_time", "email_challenges", ["ip_scope", "created_at"])
    op.create_index("ix_email_challenges_created", "email_challenges", ["created_at"])
    op.create_table(
        "account_invitations",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.CheckConstraint("remaining >= 0", name="ck_account_invite_remaining"),
    )


def downgrade():
    op.drop_table("account_invitations")
    op.drop_table("email_challenges")
    op.drop_index("ix_users_email", table_name="users")
    for table, columns in (
        ("users", ("email", "email_verified_at")),
        ("auth_sessions", ("device",)),
        ("user_settings", ("ai_daily_limit", "ai_intro_dismissed")),
        ("ai_jobs", ("credential_ref", "credential_session_id")),
        ("ai_usage_logs", ("credential_ref",)),
    ):
        for column in columns:
            op.drop_column(table, column)
