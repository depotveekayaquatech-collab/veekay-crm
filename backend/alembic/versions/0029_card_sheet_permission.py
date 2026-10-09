"""reserved developer-only permission cards.sheet (cards from an uploaded sheet)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-09
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'cards.sheet'")).first():
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'cards.sheet', :d)"),
            {"i": uuid.uuid4(), "d": "Cards from an uploaded sheet, behind an access code (developer only for now)"},
        )
    bind.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
        "SELECT r.id, p.id, now(), now() FROM roles r, permissions p WHERE r.code = 'developer' AND p.code = 'cards.sheet' ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'cards.sheet'"))
