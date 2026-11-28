"""Record the owner's choice to display the original meal photo."""

from alembic import op
import sqlalchemy as sa


revision = '0009_meal_photo_display'
down_revision = '0008_friend_sharing'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('meal_media', sa.Column('use_original', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('meal_media') as table:
        table.drop_column('use_original')
