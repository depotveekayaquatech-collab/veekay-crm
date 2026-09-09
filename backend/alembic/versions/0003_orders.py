"""phase 3b: orders table; drop unused order_assignments

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("order_assignments")

    op.create_table(
        "orders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("order_number", sa.String(64), nullable=False, index=True),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending", index=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("customer_name", sa.String(128), nullable=True),
        sa.Column("customer_phone", sa.String(32), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_note", sa.String(500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "order_number", name="uq_order_org_number"),
    )


def downgrade() -> None:
    op.drop_table("orders")
    op.create_table(
        "order_assignments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("external_order_id", sa.String(64), nullable=False, index=True),
        sa.Column("assigned_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("assigned_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "external_order_id", name="uq_order_assignment_org_order"),
    )
