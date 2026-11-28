"""Keep optional processing durations with the owner's sticker job."""

from alembic import op
import sqlalchemy as sa


revision = '0010_sticker_timings'
down_revision = '0009_meal_photo_display'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sticker_jobs', sa.Column('timings', sa.JSON(none_as_null=True), nullable=True))


def downgrade():
    with op.batch_alter_table('sticker_jobs') as table:
        table.drop_column('timings')
