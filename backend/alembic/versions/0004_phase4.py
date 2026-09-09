"""phase 4: employee-code login, store fields+status, state assignments,
order entries, per-user permissions; drop order-lifecycle tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- drop the guessed order-lifecycle model ---
    op.drop_table("orders")
    op.drop_table("employee_stores")

    # --- users: employee_code + platform, email now optional ---
    op.add_column("users", sa.Column("employee_code", sa.String(32), nullable=True))
    op.add_column(
        "users",
        sa.Column("platform_organization_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_platform_org", "users", "organizations",
        ["platform_organization_id"], ["id"], ondelete="SET NULL",
    )
    # Backfill a unique code for existing rows, then lock it down.
    op.execute("UPDATE users SET employee_code = 'U-' || substr(replace(id::text,'-',''), 1, 8) WHERE employee_code IS NULL")
    op.alter_column("users", "employee_code", nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
    op.create_index("ix_users_employee_code", "users", ["employee_code"])
    op.create_unique_constraint("uq_org_employee_code", "users", ["organization_id", "employee_code"])

    # --- stores: descriptive fields + LIVE/PENDING/CLOSE status ---
    for col in ("state", "city", "poc_name", "poc_number", "vendor_name", "vendor_number"):
        length = 64 if col in ("state", "city") else (32 if col.endswith("number") else 128)
        op.add_column("stores", sa.Column(col, sa.String(length), nullable=True))
    op.add_column("stores", sa.Column("status", sa.String(16), nullable=False, server_default="LIVE"))
    op.execute("UPDATE stores SET status = CASE WHEN is_active THEN 'LIVE' ELSE 'CLOSE' END")
    op.drop_column("stores", "is_active")
    op.create_index("ix_stores_state", "stores", ["state"])
    op.create_index("ix_stores_status", "stores", ["status"])

    # --- state -> employee assignment ---
    op.create_table(
        "state_assignments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("partner_organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("state", sa.String(64), nullable=False, index=True),
        sa.Column("assigned_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("partner_organization_id", "state", name="uq_state_assignment_partner_state"),
    )

    # --- daily bottle-count entries ---
    op.create_table(
        "order_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_date", sa.Date, nullable=False, index=True),
        sa.Column("bottle_count", sa.Integer, nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="employee"),
        sa.Column("marked_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "order_date", name="uq_order_entry_store_date"),
    )

    # --- direct per-user permission grants ---
    op.create_table(
        "user_permissions",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", pg.UUID(as_uuid=True), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),
    )


def downgrade() -> None:
    op.drop_table("user_permissions")
    op.drop_table("order_entries")
    op.drop_table("state_assignments")

    op.drop_index("ix_stores_status", table_name="stores")
    op.drop_index("ix_stores_state", table_name="stores")
    op.add_column("stores", sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()))
    op.execute("UPDATE stores SET is_active = (status = 'LIVE')")
    op.drop_column("stores", "status")
    for col in ("vendor_number", "vendor_name", "poc_number", "poc_name", "city", "state"):
        op.drop_column("stores", col)

    op.drop_constraint("uq_org_employee_code", "users", type_="unique")
    op.drop_index("ix_users_employee_code", table_name="users")
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
    op.drop_constraint("fk_users_platform_org", "users", type_="foreignkey")
    op.drop_column("users", "platform_organization_id")
    op.drop_column("users", "employee_code")

    op.create_table(
        "employee_stores",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "store_id", name="uq_employee_store"),
    )
    op.create_table(
        "orders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_number", sa.String(64), nullable=False),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("customer_name", sa.String(128), nullable=True),
        sa.Column("customer_phone", sa.String(32), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_note", sa.String(500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "order_number", name="uq_order_org_number"),
    )
