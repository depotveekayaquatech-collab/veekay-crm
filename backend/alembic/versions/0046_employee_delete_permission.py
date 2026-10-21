"""reserved developer-only permission employees.delete (permanently delete a deactivated user)

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-21
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'employees.delete'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'employees.delete', :d)"),
            {"i": uuid.uuid4(), "d": "Permanently delete a deactivated user and their attendance, leave and salary records (developer only)"},
        )
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
        "SELECT r.id, p.id, now(), now() FROM roles r, permissions p WHERE r.code = 'developer' AND p.code = 'employees.delete' ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'employees.delete'"))
