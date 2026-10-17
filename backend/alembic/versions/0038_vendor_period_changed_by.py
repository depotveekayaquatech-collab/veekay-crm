"""store_vendor_periods.changed_by_name: who made each vendor change

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("store_vendor_periods", sa.Column("changed_by_name", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("store_vendor_periods", "changed_by_name")
