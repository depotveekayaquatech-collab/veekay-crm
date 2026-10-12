"""staff notifications + push devices, and sent bill reminders

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033"
down_revision = "0032"
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
    op.create_table(
        "staff_notifications", *_base(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("ref_id", sa.String(64)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_staff_notifications_user_id", "staff_notifications", ["user_id"])
    op.create_table(
        "staff_devices", *_base(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_devices_user_id", "staff_devices", ["user_id"])
    op.create_table(
        "bill_reminders", *_base(),
        sa.Column("document_id", UUID, sa.ForeignKey("compliance_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.UniqueConstraint("document_id", "stage", name="uq_bill_reminder_stage"),
    )
    op.create_index("ix_bill_reminders_document_id", "bill_reminders", ["document_id"])


def downgrade() -> None:
    op.drop_table("bill_reminders")
    op.drop_table("staff_devices")
    op.drop_table("staff_notifications")
