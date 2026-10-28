"""capping history: a row may say "no capping from this date" (capping NULL)

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-28

Removing a store's capping is a change like any other: a history row with no capping from a date. The days before it keep the capping they had, so the record
of what was in force stays complete. capping_history.capping becomes nullable and the check allows NULL or a whole number of 1 or more. Nothing else changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("capping_history", "capping", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint("ck_capping_history_capping", "capping_history", type_="check")
    op.create_check_constraint("ck_capping_history_capping", "capping_history", "capping IS NULL OR capping >= 1")


def downgrade() -> None:
    # A "no capping" row cannot be kept in the old shape: those rows are dropped (the earlier capping then applies again).
    op.execute("DELETE FROM capping_history WHERE capping IS NULL")
    op.drop_constraint("ck_capping_history_capping", "capping_history", type_="check")
    op.create_check_constraint("ck_capping_history_capping", "capping_history", "capping >= 1")
    op.alter_column("capping_history", "capping", existing_type=sa.Integer(), nullable=False)
