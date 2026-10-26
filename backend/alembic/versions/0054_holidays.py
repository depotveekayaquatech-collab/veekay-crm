"""company holidays

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-26

A holiday is a date nobody is expected to work: attendance does not count it as an absence, salary pays it like a weekly off, leave does not use a
day on it, and performance does not expect entries on it. One row per organisation and date. A new table only: nothing existing is touched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holiday_date", sa.Date, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "holiday_date", name="uq_holiday_org_date"),
    )
    op.create_index("ix_holidays_organization_id", "holidays", ["organization_id"])
    op.create_index("ix_holidays_holiday_date", "holidays", ["holiday_date"])


def downgrade() -> None:
    op.drop_table("holidays")
