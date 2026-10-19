"""cash purchases: keep each proof file's hash, and a pointer when a possible duplicate was confirmed as different

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cash_purchases", sa.Column("proof_sha256", sa.String(64), nullable=True))
    op.create_index("ix_cash_purchases_proof_sha256", "cash_purchases", ["proof_sha256"])
    op.add_column("cash_purchases", sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_cash_purchases_duplicate_of", "cash_purchases", "cash_purchases", ["duplicate_of_id"], ["id"], ondelete="SET NULL")
    # the duplicate check looks for the same date and amount
    op.create_index("ix_cash_purchases_date_amount", "cash_purchases", ["purchase_date", "amount"])


def downgrade() -> None:
    op.drop_index("ix_cash_purchases_date_amount", table_name="cash_purchases")
    op.drop_constraint("fk_cash_purchases_duplicate_of", "cash_purchases", type_="foreignkey")
    op.drop_column("cash_purchases", "duplicate_of_id")
    op.drop_index("ix_cash_purchases_proof_sha256", table_name="cash_purchases")
    op.drop_column("cash_purchases", "proof_sha256")
