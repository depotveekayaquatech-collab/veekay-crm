"""capping zero days: mark a store's capping as 0 for specific days

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-27

capping_zero_days   one row per (store, day) on which the capping is 0, whatever capping_history says. Unique on (store_id, day). Nothing existing is touched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capping_zero_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "day", name="uq_capping_zero_day_store_day"),
    )
    op.create_index("ix_capping_zero_days_store_id", "capping_zero_days", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_capping_zero_days_store_id", table_name="capping_zero_days")
    op.drop_table("capping_zero_days")
