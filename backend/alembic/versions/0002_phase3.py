"""phase 3: regions, stores, employee_stores, order_assignments, users.region_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_region_org_code"),
    )

    op.create_table(
        "stores",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("partner_organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("region_id", pg.UUID(as_uuid=True), sa.ForeignKey("regions.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("external_code", sa.String(64), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("partner_organization_id", "external_code", name="uq_store_partner_code"),
    )

    op.create_table(
        "employee_stores",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "store_id", name="uq_employee_store"),
    )

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

    op.add_column("users", sa.Column("region_id", pg.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_users_region_id", "users", "regions", ["region_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_users_region_id", "users", ["region_id"])


def downgrade() -> None:
    op.drop_index("ix_users_region_id", table_name="users")
    op.drop_constraint("fk_users_region_id", "users", type_="foreignkey")
    op.drop_column("users", "region_id")
    op.drop_table("order_assignments")
    op.drop_table("employee_stores")
    op.drop_table("stores")
    op.drop_table("regions")
