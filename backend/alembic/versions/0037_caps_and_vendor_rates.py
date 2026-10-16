"""store_caps (Zepto monthly capping) and vendor_rates (city-wise vendor rate)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "store_caps",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", UUID, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("monthly_cap", sa.Integer, nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="manual"),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("monthly_cap >= 0", name="ck_store_caps_non_negative"),
    )
    op.create_table(
        "vendor_rates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("partner_organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("city_key", sa.String(64), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("store_id", UUID, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=True),
        sa.Column("rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("rate >= 0", name="ck_vendor_rates_non_negative"),
    )
    op.create_index("ix_vendor_rates_lookup", "vendor_rates", ["partner_organization_id", "city_key", "store_id", "effective_from"])


def downgrade() -> None:
    op.drop_table("vendor_rates")
    op.drop_table("store_caps")
