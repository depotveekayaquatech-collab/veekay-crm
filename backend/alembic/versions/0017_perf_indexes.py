"""performance indexes: activity log by date, entries by date+store

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-06
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The Activity page lists newest-first per organisation; without this it sorts the whole table on every load.
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["organization_id", "created_at"])
    # Daily roll-ups filter by date first, then sum per store.
    op.create_index("ix_order_entries_date_store", "order_entries", ["order_date", "store_id"])


def downgrade() -> None:
    op.drop_index("ix_order_entries_date_store", table_name="order_entries")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
