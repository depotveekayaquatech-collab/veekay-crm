"""entries.view_all permission: a Level 1 employee who can SEE every entry of the stores they mark (read-only)

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-27

Nobody holds it until an administrator ticks it for a person (not given to any role). It changes only what the person SEES in the order calendar and the
month's bottles in Vendors; marking, store scope and corrections are exactly as for any Level 1 employee.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

CODE = "entries.view_all"
DESCRIPTION = "See every entry of the stores you can mark, read-only (you still mark like any Level 1 employee: no corrections, no history)"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": CODE}).scalar() is None:
        bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": uuid.uuid4(), "c": CODE, "d": DESCRIPTION})


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": CODE})
