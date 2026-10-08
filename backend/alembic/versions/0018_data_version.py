"""shared data-version counter for the read cache

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-06
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Bumped after every successful write request; workers only serve cached roll-ups while it is unchanged.
    op.execute("CREATE SEQUENCE IF NOT EXISTS app_data_version")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS app_data_version")
