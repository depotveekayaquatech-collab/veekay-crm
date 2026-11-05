"""capping.planner permission (Smart Capping Planner); admins get it

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-05

The planner reads stores, cappings and the month's entries and writes nothing. Adds one permission row and grants it to the admin role; a "manager",
Team Lead or reviewer gets it only when an admin ticks it for them. Safe to run again.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

PERMISSION = "capping.planner"
DESCRIPTION = "Smart Capping Planner: analyse store capping capacity, plan a target over it and export (read only, changes no entry)"


def upgrade() -> None:
    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": PERMISSION}).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": pid, "c": PERMISSION, "d": DESCRIPTION})
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": PERMISSION})
