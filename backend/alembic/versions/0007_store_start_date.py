"""stores.start_date

The day supply to a store began (optional).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("stores", "start_date")
