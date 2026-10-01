"""tickets, partner accounts

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-01
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("tickets.view", "View tickets for your stores"),
    ("tickets.create", "Raise tickets"),
    ("tickets.manage", "Manage every ticket: assign, change status, see all regions and insights"),
]


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", pg.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_to_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("number", name="uq_tickets_number"),
    )
    for col in ("organization_id", "store_id", "partner_organization_id", "category", "status", "assigned_to_user_id"):
        op.create_index(f"ix_tickets_{col}", "tickets", [col])

    op.create_table(
        "ticket_comments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=True), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("event", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])

    # Permissions, the 'partner' role, and who gets what by default.
    bind = op.get_bind()
    perm_ids: dict[str, uuid.UUID] = {}
    for code, desc in NEW_PERMISSIONS:
        row = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).first()
        pid = row[0] if row else uuid.uuid4()
        if not row:
            bind.execute(
                sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"),
                {"i": pid, "c": code, "d": desc},
            )
        perm_ids[code] = pid

    if not bind.execute(sa.text("SELECT id FROM roles WHERE code = 'partner'")).first():
        bind.execute(
            sa.text(
                "INSERT INTO roles (id, code, name, created_at, updated_at) "
                "VALUES (:i, 'partner', 'Partner account', now(), now())"
            ),
            {"i": uuid.uuid4()},
        )

    # Admins can do everything, including managing tickets.
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        for pid in perm_ids.values():
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                    "VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"r": role_id, "p": pid},
            )
    # Existing field employees start receiving (and can raise) tickets for their own stores.
    for (user_id,) in bind.execute(
        sa.text("SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code = 'employee'")
    ).all():
        for code in ("tickets.view", "tickets.create"):
            bind.execute(
                sa.text(
                    "INSERT INTO user_permissions (user_id, permission_id, created_at, updated_at) "
                    "VALUES (:u, :p, now(), now()) ON CONFLICT DO NOTHING"
                ),
                {"u": user_id, "p": perm_ids[code]},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM permissions WHERE code IN ('tickets.view', 'tickets.create', 'tickets.manage')"))
    bind.execute(sa.text("DELETE FROM roles WHERE code = 'partner'"))
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
