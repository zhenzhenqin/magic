"""Add private stickers and backfill the food catalog from existing meal items."""

from datetime import UTC, datetime
import re
import unicodedata
from uuid import uuid4

from alembic import context, op
import sqlalchemy as sa


revision = '0007_stickers_catalog'
down_revision = '0006_deepseek_budget'
branch_labels = None
depends_on = None


def backfill():
    db = op.get_bind()
    aliases = {
        "牛角包": "可颂", "羊角面包": "可颂", "牛角面包": "可颂", "原味可颂": "可颂",
        "可颂(牛角面包)": "可颂", "可颂(牛角包)": "可颂", "可颂牛角面包": "可颂",
        "西红柿炒鸡蛋": "番茄炒蛋", "番茄炒鸡蛋": "番茄炒蛋",
    }
    rows = db.execute(sa.text(
        "SELECT meals.user_id, meal_items.id, food_name, category FROM meal_items "
        "JOIN meals ON meals.id = meal_items.meal_id ORDER BY meals.eaten_at DESC, meal_items.id"
    ))
    entries = {}
    now = datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ")
    for owner, item, name, category in rows:
        key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name).casefold())
        key = aliases.get(key, key)[:80]
        identifier = entries.get((owner, key))
        if identifier is None:
            identifier = str(uuid4())
            entries[(owner, key)] = identifier
            db.execute(sa.text(
                "INSERT INTO food_catalog (id,user_id,canonical_name,display_name,category,is_favorite,category_custom,created_at,updated_at) "
                "VALUES (:id,:owner,:key,:name,:category,0,0,:now,:now)"
            ), dict(id=identifier, owner=owner, key=key, name=key if key in aliases.values() else name, category=category, now=now))
            db.execute(sa.text("INSERT INTO catalog_names VALUES (:owner,:key,:id)"),
                       dict(owner=owner, key=key, id=identifier))
        db.execute(sa.text("INSERT INTO catalog_links VALUES (:item,:owner,:id)"),
                   dict(item=item, owner=owner, id=identifier))


def upgrade():
    op.create_table('sticker_runtime',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('heartbeat', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('food_catalog',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('canonical_name', sa.String(length=80), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=True),
    sa.Column('cover_media_id', sa.String(length=36), nullable=True),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('category_custom', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['cover_media_id'], ['media_assets.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'id')
    )
    op.create_index(op.f('ix_food_catalog_user_id'), 'food_catalog', ['user_id'], unique=False)
    op.create_table('media_derivatives',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('source_media_id', sa.String(length=36), nullable=False),
    sa.Column('source_digest', sa.String(length=64), nullable=False),
    sa.Column('recipe', sa.String(length=64), nullable=False),
    sa.Column('derivative_type', sa.String(length=12), nullable=False),
    sa.Column('storage_key', sa.String(length=96), nullable=False),
    sa.Column('cutout_key', sa.String(length=96), nullable=False),
    sa.Column('thumbnail_key', sa.String(length=96), nullable=False),
    sa.Column('content_type', sa.String(length=32), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('model_name', sa.String(length=32), nullable=False),
    sa.Column('model_version', sa.String(length=64), nullable=False),
    sa.Column('processing_version', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id', 'source_media_id'], ['media_assets.user_id', 'media_assets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cutout_key'),
    sa.UniqueConstraint('source_media_id'),
    sa.UniqueConstraint('storage_key'),
    sa.UniqueConstraint('thumbnail_key')
    )
    op.create_index(op.f('ix_media_derivatives_user_id'), 'media_derivatives', ['user_id'], unique=False)
    op.create_table('sticker_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('source_media_id', sa.String(length=36), nullable=False),
    sa.Column('source_digest', sa.String(length=64), nullable=False),
    sa.Column('recipe', sa.String(length=64), nullable=False),
    sa.Column('crop', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('claim', sa.String(length=36), nullable=True),
    sa.Column('lease_until', sa.DateTime(), nullable=True),
    sa.Column('error_code', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')", name='ck_sticker_job_status'),
    sa.ForeignKeyConstraint(['user_id', 'source_media_id'], ['media_assets.user_id', 'media_assets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_media_id')
    )
    op.create_index('ix_sticker_jobs_queue', 'sticker_jobs', ['status', 'updated_at'], unique=False)
    op.create_index(op.f('ix_sticker_jobs_user_id'), 'sticker_jobs', ['user_id'], unique=False)
    op.create_table('catalog_links',
    sa.Column('item_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('catalog_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['meal_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id', 'catalog_id'], ['food_catalog.user_id', 'food_catalog.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id')
    )
    op.create_index(op.f('ix_catalog_links_catalog_id'), 'catalog_links', ['catalog_id'], unique=False)
    op.create_table('catalog_names',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('catalog_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id', 'catalog_id'], ['food_catalog.user_id', 'food_catalog.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'name')
    )
    op.create_index(op.f('ix_catalog_names_catalog_id'), 'catalog_names', ['catalog_id'], unique=False)
    if not context.is_offline_mode():
        backfill()


def downgrade():
    op.drop_index(op.f('ix_catalog_names_catalog_id'), table_name='catalog_names')
    op.drop_table('catalog_names')
    op.drop_index(op.f('ix_catalog_links_catalog_id'), table_name='catalog_links')
    op.drop_table('catalog_links')
    op.drop_index(op.f('ix_sticker_jobs_user_id'), table_name='sticker_jobs')
    op.drop_index('ix_sticker_jobs_queue', table_name='sticker_jobs')
    op.drop_table('sticker_jobs')
    op.drop_index(op.f('ix_media_derivatives_user_id'), table_name='media_derivatives')
    op.drop_table('media_derivatives')
    op.drop_index(op.f('ix_food_catalog_user_id'), table_name='food_catalog')
    op.drop_table('food_catalog')
    op.drop_table('sticker_runtime')
