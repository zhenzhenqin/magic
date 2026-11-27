"""Initialize DeepSeek's separate cap without modifying Qwen's history."""

import sqlalchemy as sa
from alembic import op

revision = "0006_deepseek_budget"
down_revision = "0005_ai_processing_context"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text(
        "INSERT INTO ai_call_budgets (provider, spent) SELECT 'deepseek', 0 "
        "WHERE NOT EXISTS (SELECT 1 FROM ai_call_budgets WHERE provider = 'deepseek')"
    ))


def downgrade():
    # Retain any spend across a later upgrade. Delete only an unused ledger row.
    op.execute(sa.text("DELETE FROM ai_call_budgets WHERE provider = 'deepseek' AND spent = 0"))
