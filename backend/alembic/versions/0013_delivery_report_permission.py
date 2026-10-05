"""delivery report download permission for partner accounts

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-02
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'reports.delivery'")).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'reports.delivery', :d)"),
            {"i": pid, "d": "Download delivery reports (partner accounts)"},
        )
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                "VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"
            ),
            {"r": role_id, "p": pid},
        )
    # Existing partner accounts could already see their daily entries; let them download the report too.
    for (user_id,) in bind.execute(
        sa.text("SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code = 'partner'")
    ).all():
        bind.execute(
            sa.text(
                "INSERT INTO user_permissions (user_id, permission_id, created_at, updated_at) "
                "VALUES (:u, :p, now(), now()) ON CONFLICT DO NOTHING"
            ),
            {"u": user_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'reports.delivery'"))
