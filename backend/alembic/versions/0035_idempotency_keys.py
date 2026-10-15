"""idempotency_keys: replay-safe create requests (tickets, replies, documents, cash purchases)

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("state", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("response", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("owner", "endpoint", "key", name="uq_idempotency_owner_endpoint_key"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
