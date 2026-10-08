"""cash purchases: payment proof instead of 'paid to'

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("cash_purchases", "paid_to")
    op.add_column("cash_purchases", sa.Column("proof_key", sa.String(512), nullable=True))
    op.add_column("cash_purchases", sa.Column("proof_name", sa.String(255), nullable=True))
    op.add_column("cash_purchases", sa.Column("proof_content_type", sa.String(64), nullable=True))
    op.add_column("cash_purchases", sa.Column("proof_size_bytes", sa.BigInteger, nullable=True))


def downgrade() -> None:
    for c in ("proof_size_bytes", "proof_content_type", "proof_name", "proof_key"):
        op.drop_column("cash_purchases", c)
    op.add_column("cash_purchases", sa.Column("paid_to", sa.String(120), nullable=True))
