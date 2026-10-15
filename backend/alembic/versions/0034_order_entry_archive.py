"""order_entry_archive: safety copy of order history taken when stores are wiped

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "order_entry_archive",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("partner_organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_code", sa.String(64), nullable=False),
        sa.Column("store_name", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("city", sa.String(64), nullable=True),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("bottle_count", sa.Integer, nullable=False),
        sa.Column("cash_adjustment", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False, server_default="stores_wiped"),
        sa.UniqueConstraint("partner_organization_id", "external_code", "order_date", name="uq_order_archive_store_date"),
    )
    op.create_index("ix_order_entry_archive_organization_id", "order_entry_archive", ["organization_id"])
    op.create_index("ix_order_entry_archive_partner_organization_id", "order_entry_archive", ["partner_organization_id"])
    op.create_index("ix_order_entry_archive_external_code", "order_entry_archive", ["external_code"])


def downgrade() -> None:
    op.drop_table("order_entry_archive")
