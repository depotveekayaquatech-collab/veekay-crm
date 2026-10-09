"""several regions per employee + excluded states / cities

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_regions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("region_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_employee_regions_region_id", "employee_regions", ["region_id"])
    op.create_table(
        "employee_exclusions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("value", sa.String(128), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "value", name="uq_employee_exclusion"),
        sa.CheckConstraint("kind IN ('state','city')", name="ck_employee_exclusion_kind"),
    )
    op.create_index("ix_employee_exclusions_user_id", "employee_exclusions", ["user_id"])
    # Everyone's current region becomes their first (and only) region.
    op.execute("INSERT INTO employee_regions (user_id, region_id) SELECT id, region_id FROM users WHERE region_id IS NOT NULL")


def downgrade() -> None:
    op.drop_table("employee_exclusions")
    op.drop_table("employee_regions")
