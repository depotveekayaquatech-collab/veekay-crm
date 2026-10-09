"""reserved developer-only permission bottles.delete 

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-09
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'bottles.delete'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'bottles.delete', :d)"),
            {"i": uuid.uuid4(), "d": "Permanently delete bottle QR codes so they can never be used again (developer only)"},
        )
    for code in ("bottles.delete",):
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                "SELECT r.id, p.id, now(), now() FROM roles r, permissions p "
                "WHERE r.code = 'developer' AND p.code = :c ON CONFLICT DO NOTHING"
            ),
            {"c": code},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'bottles.delete'"))
