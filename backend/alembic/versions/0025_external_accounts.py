"""vendor / POC logins prepared for the future app (separate from CRM users)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("phone", sa.String(64)),
        sa.Column("platforms", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("store_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_external_account_email"),
        sa.CheckConstraint("kind IN ('vendor','poc')", name="ck_external_account_kind"),
    )
    op.create_index("ix_external_accounts_organization_id", "external_accounts", ["organization_id"])
    op.create_index("ix_external_accounts_kind", "external_accounts", ["kind"])
    op.create_table(
        "external_account_stores",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("external_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_external_account_stores_store_id", "external_account_stores", ["store_id"])


def downgrade() -> None:
    op.drop_table("external_account_stores")
    op.drop_table("external_accounts")
