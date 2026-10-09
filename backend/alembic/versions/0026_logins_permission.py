"""logins.view permission (vendor / POC logins page); admins get it

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-09
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'logins.view'")).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'logins.view', :d)"),
            {"i": pid, "d": "View and export the vendor / POC logins prepared for the mobile app"},
        )
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'logins.view'"))
