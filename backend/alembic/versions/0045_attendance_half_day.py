"""attendance_records.half_day: a developer can mark a worked day as a half day (payroll counts it as 0.5)

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("attendance_records", sa.Column("half_day", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("attendance_records", "half_day")
