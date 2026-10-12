"""vendor / POC sign-in: sessions table + lockout columns on external_accounts

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("external_accounts", sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default="0"))
    op.add_column("external_accounts", sa.Column("locked_until", sa.DateTime(timezone=True)))
    op.create_table(
        "external_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", postgresql.UUID(as_uuid=True)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_external_sessions_account_id", "external_sessions", ["account_id"])
    op.create_index("ix_external_sessions_family_id", "external_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_table("external_sessions")
    op.drop_column("external_accounts", "locked_until")
    op.drop_column("external_accounts", "failed_login_attempts")
