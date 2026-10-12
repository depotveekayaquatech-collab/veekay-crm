"""vendor / POC actions: ticket photos, delivery confirmations, devices + notifications, comment author label

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _base() -> list:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("ticket_comments", sa.Column("author_label", sa.String(128)))
    op.create_table(
        "ticket_attachments", *_base(),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comment_id", UUID, sa.ForeignKey("ticket_comments.id", ondelete="CASCADE")),
        sa.Column("file_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("uploaded_by_account_id", UUID, sa.ForeignKey("external_accounts.id", ondelete="SET NULL")),
    )
    op.create_index("ix_ticket_attachments_ticket_id", "ticket_attachments", ["ticket_id"])
    op.create_table(
        "delivery_confirmations", *_base(),
        sa.Column("account_id", UUID, sa.ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", UUID, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_date", sa.Date, nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("expected_qty", sa.Integer),
        sa.Column("received_qty", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id", ondelete="SET NULL")),
        sa.UniqueConstraint("account_id", "store_id", "delivery_date", name="uq_delivery_account_store_date"),
        sa.CheckConstraint("outcome IN ('RECEIVED','SHORT','DAMAGED')", name="ck_delivery_outcome"),
    )
    op.create_index("ix_delivery_confirmations_account_id", "delivery_confirmations", ["account_id"])
    op.create_index("ix_delivery_confirmations_store_id", "delivery_confirmations", ["store_id"])
    op.create_index("ix_delivery_confirmations_delivery_date", "delivery_confirmations", ["delivery_date"])
    op.create_table(
        "external_devices", *_base(),
        sa.Column("account_id", UUID, sa.ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_external_devices_account_id", "external_devices", ["account_id"])
    op.create_table(
        "external_notifications", *_base(),
        sa.Column("account_id", UUID, sa.ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("ref_id", sa.String(64)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_external_notifications_account_id", "external_notifications", ["account_id"])


def downgrade() -> None:
    op.drop_table("external_notifications")
    op.drop_table("external_devices")
    op.drop_table("delivery_confirmations")
    op.drop_table("ticket_attachments")
    op.drop_column("ticket_comments", "author_label")
