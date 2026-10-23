"""readable (encrypted) copy of staff passwords for the developer + reserved permission employees.view_password

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-23

users.password_enc holds the same password as password_hash, encrypted (Fernet). Sign-in still only checks the bcrypt hash. Existing
accounts start empty: bcrypt can't be reversed, so their copy is filled the next time that person signs in or has the password reset.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_enc", sa.Text(), nullable=True))
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'employees.view_password'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'employees.view_password', :d)"),
            {"i": uuid.uuid4(), "d": "See every user's current password and how long ago it changed (developer only)"},
        )
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
        "SELECT r.id, p.id, now(), now() FROM roles r, permissions p WHERE r.code = 'developer' AND p.code = 'employees.view_password' ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'employees.view_password'"))
    op.drop_column("users", "password_enc")
