"""entries.edit_previous permission: a Level 1 employee who may change ANY earlier entry of the stores they mark (audited)

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-28

Nobody holds it until an administrator ticks it for a person (not given to any role). With it an employee can change or clear any entry of their own stores, whoever
entered it or changed it last, for the dates still open to them (this month, and last month until the 5th). Every change is stamped with who made it and goes into the
append-only entry history like any correction; the earlier number stays in the history.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

CODE = "entries.edit_previous"
DESCRIPTION = "Change any earlier entry of the stores you mark, whoever entered it (this month, and last month until the 5th). Every change is kept in the entry history"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": CODE}).scalar() is None:
        bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": uuid.uuid4(), "c": CODE, "d": DESCRIPTION})


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": CODE})
