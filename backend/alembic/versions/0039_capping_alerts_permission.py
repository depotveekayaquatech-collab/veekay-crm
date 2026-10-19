"""capping.alerts permission (employees see over-cap / ahead-of-pace stores); admins get it

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-19
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'capping.alerts'")).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'capping.alerts', :d)"),
            {"i": pid, "d": "See capping alerts for your stores (over the monthly cap, or ahead of its pace)"},
        )
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'capping.alerts'"))
