"""Bind future recognition jobs to the processing endpoint selected at creation."""

import sqlalchemy as sa
from alembic import op

revision = "0005_ai_processing_context"
down_revision = "0004_ai_recovery"
branch_labels = None
depends_on = None


def upgrade():
    # Historical jobs have no reliable endpoint record. Keep their results and fail closed if dispatched again.
    op.add_column("ai_jobs", sa.Column("processing_fingerprint", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("ai_jobs", "processing_fingerprint")
