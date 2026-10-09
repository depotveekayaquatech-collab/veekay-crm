"""bottle QR tracking: batches, bottles (unique serials), append-only scans, bottles.* permissions

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-09
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

PERMS = [
    ("bottles.view", "View bottle QR codes, their scan history and the overdue / lost list"),
    ("bottles.scan", "Scan bottle QR codes in and out of stores"),
    ("bottles.manage", "Generate bottle QR codes, replace damaged ones and retire bottles"),
]


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def _pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _org():
    return sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "bottle_batches", _pk(), _org(),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        *_ts(),
    )
    op.create_index("ix_bottle_batches_organization_id", "bottle_batches", ["organization_id"])

    op.create_table(
        "bottles", _pk(), _org(),
        sa.Column("serial", sa.String(16), nullable=False, unique=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bottle_batches.id", ondelete="SET NULL")),
        sa.Column("seq", sa.Integer),
        sa.Column("status", sa.String(16), nullable=False, server_default="UNUSED"),
        sa.Column("current_store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="SET NULL")),
        sa.Column("last_in_at", sa.DateTime(timezone=True)),
        sa.Column("last_out_at", sa.DateTime(timezone=True)),
        sa.Column("last_scan_at", sa.DateTime(timezone=True)),
        sa.Column("replaces_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bottles.id", ondelete="SET NULL")),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bottles.id", ondelete="SET NULL")),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("retire_reason", sa.String(255)),
        *_ts(),
    )
    op.create_index("ix_bottles_organization_id", "bottles", ["organization_id"])
    op.create_index("ix_bottles_current_store_id", "bottles", ["current_store_id"])
    op.create_index("ix_bottles_batch_seq", "bottles", ["batch_id", "seq"])
    op.create_index("ix_bottles_status_last_in", "bottles", ["organization_id", "status", "last_in_at"])

    op.create_table(
        "bottle_scans", _pk(), _org(),
        sa.Column("bottle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bottles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="SET NULL")),
        sa.Column("store_name", sa.String(255)),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("scanned_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("scanned_by_name", sa.String(255)),
        sa.Column("client_scan_id", sa.String(128), unique=True),
        sa.Column("warning", sa.String(255)),
        sa.CheckConstraint("direction IN ('IN','OUT')", name="ck_bottle_scan_direction"),
        *_ts(),
    )
    op.create_index("ix_bottle_scans_organization_id", "bottle_scans", ["organization_id"])
    op.create_index("ix_bottle_scans_store_id", "bottle_scans", ["store_id"])
    op.create_index("ix_bottle_scans_scanned_at", "bottle_scans", ["scanned_at"])
    op.create_index("ix_bottle_scans_bottle_time", "bottle_scans", ["bottle_id", "scanned_at"])

    # Permissions; admins get all three.
    bind = op.get_bind()
    for code, desc in PERMS:
        pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).scalar()
        if pid is None:
            pid = uuid.uuid4()
            bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": pid, "c": code, "d": desc})
        for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
            bind.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
                {"r": role_id, "p": pid},
            )


def downgrade() -> None:
    op.drop_table("bottle_scans")
    op.drop_table("bottles")
    op.drop_table("bottle_batches")
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code IN ('bottles.view', 'bottles.scan', 'bottles.manage')"))
