"""entries.view_all and entries.edit_previous become the default of every Level 1 employee, so they are no longer permissions

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-29

Every Level 1 employee now sees every entry of the stores they mark (read-only) and may change any entry of those stores in the dates still open to them (this month,
and last month until the 5th), audited like any correction. Nothing needs ticking, so the two per-person permissions are removed from the catalogue, together with
any grant of them, instead of leaving a checkbox that does nothing.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

CODES = {
    "entries.view_all": "See every entry of the stores you can mark, read-only (you still mark like any Level 1 employee: no corrections, no history)",
    "entries.edit_previous": "Change any earlier entry of the stores you mark, whoever entered it (this month, and last month until the 5th). Every change is kept in the entry history",
}


def upgrade() -> None:
    bind = op.get_bind()
    for code in CODES:
        pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).scalar()
        if pid is None:
            continue
        bind.execute(sa.text("DELETE FROM user_permissions WHERE permission_id = :p"), {"p": pid})
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :p"), {"p": pid})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :p"), {"p": pid})


def downgrade() -> None:
    bind = op.get_bind()
    for code, description in CODES.items():
        if bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).scalar() is None:
            bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": uuid.uuid4(), "c": code, "d": description})
