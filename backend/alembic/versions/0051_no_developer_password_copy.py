"""a developer's password is never kept in readable form: drop any copy already stored

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-23
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET password_enc = NULL WHERE password_enc IS NOT NULL AND id IN "
        "(SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code = 'developer')"
    )


def downgrade() -> None:
    pass
