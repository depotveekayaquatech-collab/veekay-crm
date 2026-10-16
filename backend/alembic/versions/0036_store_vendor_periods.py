"""store_vendor_periods: who supplied each store and when (vendor history)

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "store_vendor_periods",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", UUID, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_name", sa.String(128), nullable=False),
        sa.Column("vendor_number", sa.String(32), nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("start_confirmed", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.String(16), nullable=False, server_default="sheet"),
    )
    op.create_index("ix_store_vendor_periods_store_id", "store_vendor_periods", ["store_id"])
    # at most one current (open) vendor per store
    op.create_index("uq_store_vendor_one_open", "store_vendor_periods", ["store_id"], unique=True, postgresql_where=sa.text("end_date IS NULL"))
    # every store that has a vendor today starts with that vendor as its current, open period
    op.execute(
        """
        INSERT INTO store_vendor_periods (id, created_at, updated_at, store_id, vendor_name, vendor_number, start_date, source)
        SELECT gen_random_uuid(), now(), now(), id, vendor_name, vendor_number, start_date, 'backfill'
        FROM stores WHERE vendor_name IS NOT NULL AND btrim(vendor_name) <> ''
        """
    )


def downgrade() -> None:
    op.drop_table("store_vendor_periods")
