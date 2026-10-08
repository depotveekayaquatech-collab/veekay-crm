"""developer role + the reserved 'sheets.sync' permission

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-08

The developer role is created here, by code, and is never offered in the app. Admins do NOT get 'sheets.sync'
(the full-admin shortcut in UserRepository.get_permission_codes excludes reserved permissions).
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'sheets.sync'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'sheets.sync', :d)"),
            {"i": uuid.uuid4(), "d": "Sheet sync and bulk sheet / file uploads of stores and orders (developer only)"},
        )
    if not bind.execute(sa.text("SELECT id FROM roles WHERE code = 'developer'")).first():
        bind.execute(
            sa.text("INSERT INTO roles (id, code, name, created_at, updated_at) VALUES (:i, 'developer', 'Developer', now(), now())"),
            {"i": uuid.uuid4()},
        )
    # The developer role holds ONLY this permission: no admin rights, no other pages.
    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
            "SELECT r.id, p.id, now(), now() FROM roles r, permissions p "
            "WHERE r.code = 'developer' AND p.code = 'sheets.sync' ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code = 'developer')"))
    bind.execute(sa.text("DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'developer')"))
    bind.execute(sa.text("DELETE FROM roles WHERE code = 'developer'"))
    bind.execute(sa.text("DELETE FROM permissions WHERE code = 'sheets.sync'"))
