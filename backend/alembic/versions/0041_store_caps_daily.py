"""store_caps.monthly_cap -> daily_cap: the capping sheet's number is a per-day cap (the monthly limit is that x 30)

The stored numbers are kept as they are; they are now read as bottles per day.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-19
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("store_caps", "monthly_cap", new_column_name="daily_cap")


def downgrade() -> None:
    op.alter_column("store_caps", "daily_cap", new_column_name="monthly_cap")
