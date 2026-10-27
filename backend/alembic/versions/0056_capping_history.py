"""capping history: a store's daily capping with the date each value took effect

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-27

capping_history   one row per change of a store's daily capping; unique on (store_id, effective_from); capping >= 1.
                  The capping on day D is the row with the greatest effective_from <= D.
capping.change    new permission (change a store's capping with an effective date); given to the admin role. A "manager" gets it when ticked.

Backfill (idempotent: only stores with NO history yet): every store_caps row with a daily cap of 1 or more becomes one history row, effective from the
earliest date in the store's order entries, or the 1st of the current month (Asia/Kolkata) when it has none. A store whose cap is 0 is skipped, the table
only holds 1 or more. store_caps itself is not touched: it stays the "current capping".
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

PERMISSION = "capping.change"
DESCRIPTION = "Change a store's capping with an effective date, and see the history of changes"

# Safe to run again: a store that already has any history row is left alone.
BACKFILL_SQL = """
        INSERT INTO capping_history (id, store_id, capping, effective_from, created_by, created_at)
        SELECT gen_random_uuid(), sc.store_id, sc.daily_cap,
               COALESCE(first_entry.d, date_trunc('month', now() AT TIME ZONE 'Asia/Kolkata')::date),
               sc.updated_by_user_id, now()
        FROM store_caps sc
        LEFT JOIN (SELECT store_id, min(order_date) AS d FROM order_entries GROUP BY store_id) first_entry ON first_entry.store_id = sc.store_id
        WHERE sc.daily_cap >= 1
          AND NOT EXISTS (SELECT 1 FROM capping_history h WHERE h.store_id = sc.store_id)
"""


def upgrade() -> None:
    op.create_table(
        "capping_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capping", sa.Integer, nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "effective_from", name="uq_capping_history_store_date"),
        sa.CheckConstraint("capping >= 1", name="ck_capping_history_capping"),
    )
    op.create_index("ix_capping_history_store_effective", "capping_history", ["store_id", sa.text("effective_from DESC")])

    bind = op.get_bind()
    bind.execute(sa.text(BACKFILL_SQL))

    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": PERMISSION}).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": pid, "c": PERMISSION, "d": DESCRIPTION})
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = :c"), {"c": PERMISSION})
    op.drop_index("ix_capping_history_store_effective", table_name="capping_history")
    op.drop_table("capping_history")
