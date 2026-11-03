"""Index on order_entries (organization_id, created_at): the dashboard's "marked today" figures

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-03

The admin dashboard counts what people marked today and yesterday by the moment the entry was created (not its order date), a range on created_at
that no existing index serves. Adds an index only; nothing is changed or deleted.
"""
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_order_entries_org_created ON order_entries (organization_id, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_order_entries_org_created")
