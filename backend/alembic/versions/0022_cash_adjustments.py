"""developer cash-purchase adjustments: per-entry adjustment + the developer-only history

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-08
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # order_entries.bottle_count stays the FINAL number every report reads; this is the part of it that came from
    # developer cash-purchase adjustments, so the employee's real entry is always bottle_count - cash_adjustment.
    op.add_column("order_entries", sa.Column("cash_adjustment", sa.Integer, nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_order_entry_adjustment_range", "order_entries", "cash_adjustment >= 0 AND cash_adjustment <= bottle_count"
    )

    op.create_table(
        "cash_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outlet_code", sa.String(64), nullable=False),
        sa.Column("outlet_name", sa.String(255), nullable=False),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_per_item", sa.Numeric(12, 2), nullable=False),
        sa.Column("auto_qty", sa.Integer, nullable=False),
        sa.Column("final_qty", sa.Integer, nullable=False),
        sa.Column("previous_qty", sa.Integer, nullable=False),
        sa.Column("final_order_qty", sa.Integer, nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("sync_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="Manual"),
        sa.Column("action", sa.String(32), nullable=False, server_default="Applied"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for col in ("organization_id", "batch_id", "store_id", "purchase_date", "created_at", "purchase_id"):
        op.create_index(f"ix_cash_adjustments_{col}", "cash_adjustments", [col])

    # Developer working area for "Sync Cash Purchase": one row per store purchase, editable until applied.
    op.create_table(
        "cash_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("records_found", sa.Integer, nullable=False),
        sa.Column("new_count", sa.Integer, nullable=False),
        sa.Column("changed_count", sa.Integer, nullable=False),
        sa.Column("already_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cash_sync_runs_organization_id", "cash_sync_runs", ["organization_id"])
    op.create_table(
        "cash_sync_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        # The source purchase's own id is the stable key: one working row per purchase, however often you sync.
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_per_item", sa.Numeric(12, 2), nullable=True),
        sa.Column("final_qty_override", sa.Integer, nullable=True),
        sa.Column("baseline", postgresql.JSONB, nullable=False),
        sa.Column("current_source", postgresql.JSONB, nullable=False),
        sa.Column("sync_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_qty", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "purchase_id", name="uq_cash_sync_record_purchase"),
    )
    op.create_index("ix_cash_sync_records_status", "cash_sync_records", ["status"])
    op.create_index("ix_cash_sync_records_sync_id", "cash_sync_records", ["sync_id"])

    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'cash.adjust'")).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'cash.adjust', :d)"),
            {"i": pid, "d": "Cash-purchase adjustments to the order sheet and their history (developer only)"},
        )
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
            "SELECT r.id, :p, now(), now() FROM roles r WHERE r.code = 'developer' ON CONFLICT DO NOTHING"
        ),
        {"p": pid},
    )


def downgrade() -> None:
    op.drop_table("cash_sync_records")
    op.drop_table("cash_sync_runs")
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'cash.adjust'"))
    op.drop_table("cash_adjustments")
    op.drop_constraint("ck_order_entry_adjustment_range", "order_entries", type_="check")
    op.drop_column("order_entries", "cash_adjustment")
