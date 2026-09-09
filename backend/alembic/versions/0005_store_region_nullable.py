"""phase 4.1: stores.region_id becomes nullable

A store synced from a partner sheet may have no matching zone/region (and
Zepto stores are routed by state, not region), so region membership is now
optional.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("stores", "region_id", existing_type=pg.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM stores WHERE region_id IS NULL")
    op.alter_column("stores", "region_id", existing_type=pg.UUID(as_uuid=True), nullable=False)
