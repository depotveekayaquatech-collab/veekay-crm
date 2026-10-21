"""reserved developer-only permission attendance.edit (correct a check-in time / office-or-away)

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-21
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'attendance.edit'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'attendance.edit', :d)"),
            {"i": uuid.uuid4(), "d": "Correct a person's check-in time and whether they were at the office or away (developer only)"},
        )
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
        "SELECT r.id, p.id, now(), now() FROM roles r, permissions p WHERE r.code = 'developer' AND p.code = 'attendance.edit' ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'attendance.edit'"))
