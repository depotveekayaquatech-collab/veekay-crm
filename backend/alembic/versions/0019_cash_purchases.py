"""cash purchases + their permissions

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

PERMS = [
    ("cash.view", "See every cash purchase and download the sheet"),
    ("cash.add", "Record cash purchases (you see your own entries)"),
]


def upgrade() -> None:
    op.create_table(
        "cash_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("other_reason", sa.String(300), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_to", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_cash_purchases_amount_positive"),
    )
    for col in ("organization_id", "kind", "store_id", "purchase_date", "created_by_user_id"):
        op.create_index(f"ix_cash_purchases_{col}", "cash_purchases", [col])

    bind = op.get_bind()
    ids = {}
    for code, desc in PERMS:
        pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).scalar()
        if pid is None:
            pid = uuid.uuid4()
            bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": pid, "c": code, "d": desc})
        ids[code] = pid

    def grant_role(role_code: str, codes: list[str]) -> None:
        for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = :r"), {"r": role_code}).all():
            for c in codes:
                bind.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                        "VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"
                    ),
                    {"r": role_id, "p": ids[c]},
                )

    grant_role("admin", ["cash.view", "cash.add"])
    grant_role("accountant", ["cash.view", "cash.add"])
    # Existing field employees may record purchases straight away (an admin can untick it per person).
    for (user_id,) in bind.execute(
        sa.text("SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code = 'employee'")
    ).all():
        bind.execute(
            sa.text(
                "INSERT INTO user_permissions (user_id, permission_id, created_at, updated_at) "
                "VALUES (:u, :p, now(), now()) ON CONFLICT DO NOTHING"
            ),
            {"u": user_id, "p": ids["cash.add"]},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code IN ('cash.view', 'cash.add')"))
    op.drop_table("cash_purchases")
