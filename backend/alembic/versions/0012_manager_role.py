"""custom-admin ("manager") role

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM roles WHERE code = 'manager'")).first():
        bind.execute(
            sa.text("INSERT INTO roles (id, code, name, created_at, updated_at) VALUES (:i, 'manager', 'Custom admin', now(), now())"),
            {"i": uuid.uuid4()},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM roles WHERE code = 'manager'"))
