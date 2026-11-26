"""Retain inference spending, original input and worker recovery metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_ai_recovery"
down_revision = "0003_ai_recognition"
branch_labels = None
depends_on = None

FK_NAMES = {"fk": "fk_%(table_name)s_%(column_0_name)s"}


def upgrade():
    op.add_column("ai_jobs", sa.Column("form_meal_id", sa.String(36)))
    op.add_column("ai_jobs", sa.Column("media_snapshot", sa.JSON(none_as_null=True)))
    with op.batch_alter_table("ai_usage_logs", naming_convention=FK_NAMES) as batch:
        batch.drop_constraint("fk_ai_usage_logs_user_id", type_="foreignkey")
        batch.alter_column("user_id", existing_type=sa.String(36), nullable=True)
        batch.create_foreign_key("fk_ai_usage_logs_user", "users", ["user_id"], ["id"], ondelete="SET NULL")
        batch.add_column(sa.Column("elapsed_ms", sa.Integer()))
        batch.add_column(sa.Column("error_code", sa.String(40)))
    op.create_table(
        "ai_call_budgets",
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("spent", sa.Integer(), nullable=False),
        sa.CheckConstraint("spent >= 0", name="ck_ai_call_budget_nonnegative"),
    )
    op.execute(sa.text(
        "INSERT INTO ai_call_budgets (provider, spent) SELECT 'qwen', COUNT(*) FROM ai_usage_logs "
        "WHERE provider = 'qwen' AND status NOT IN ('reserved', 'not_sent')"
    ))
    op.create_table(
        "ai_worker_heartbeats",
        sa.Column("configuration", sa.String(64), primary_key=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT COUNT(*) FROM ai_usage_logs WHERE user_id IS NULL")):
        raise RuntimeError("The previous schema cannot preserve anonymized AI usage rows.")
    op.drop_table("ai_worker_heartbeats")
    op.drop_table("ai_call_budgets")
    with op.batch_alter_table("ai_usage_logs", naming_convention=FK_NAMES) as batch:
        batch.drop_constraint("fk_ai_usage_logs_user", type_="foreignkey")
        batch.alter_column("user_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key("fk_ai_usage_logs_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch.drop_column("elapsed_ms")
        batch.drop_column("error_code")
    op.drop_column("ai_jobs", "media_snapshot")
    op.drop_column("ai_jobs", "form_meal_id")
