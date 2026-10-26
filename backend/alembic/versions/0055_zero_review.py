"""zero review: weekly review and monthly verification of stores stuck at zero

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-26

Two new tables, nothing existing is touched:
  zero_review      the current decision for one (store, week | month); unique on (store_id, period_type, period_start)
  zero_review_log  append-only history of every decision (the application only ever inserts); updates and deletes are refused by a trigger

The streak report reads a date range for many stores at once; it is served by the existing order_entries index (order_date, store_id) from 0017, so
no index is added to order_entries.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_pk = lambda: sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)  # noqa: E731
    fk = lambda name, target, nullable=False, ondelete="CASCADE": sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)  # noqa: E731

    op.create_table(
        "zero_review",
        uuid_pk(),
        fk("organization_id", "organizations.id"),
        fk("store_id", "stores.id"),
        sa.Column("period_type", sa.String(8), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("threshold_used", sa.Integer, nullable=True),
        sa.Column("longest_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        fk("reviewed_by_user_id", "users.id", nullable=True, ondelete="SET NULL"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("store_id", "period_type", "period_start", name="uq_zero_review_store_period"),
        sa.CheckConstraint("period_type IN ('week','month')", name="ck_zero_review_period_type"),
        sa.CheckConstraint("status IN ('pending','reviewed','verified','flagged')", name="ck_zero_review_status"),
    )
    op.create_index("ix_zero_review_organization_id", "zero_review", ["organization_id"])
    op.create_index("ix_zero_review_store_id", "zero_review", ["store_id"])
    op.create_index("ix_zero_review_period_start", "zero_review", ["period_start"])

    op.create_table(
        "zero_review_log",
        uuid_pk(),
        fk("organization_id", "organizations.id"),
        fk("store_id", "stores.id", nullable=True, ondelete="SET NULL"),
        sa.Column("period_type", sa.String(8), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(10), nullable=True),
        sa.Column("to_status", sa.String(10), nullable=True),
        sa.Column("threshold_used", sa.Integer, nullable=True),
        sa.Column("longest_streak", sa.Integer, nullable=True),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("remark", sa.Text, nullable=True),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.Text, nullable=True),
        sa.Column("actor_code", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_zero_review_log_organization_id", "zero_review_log", ["organization_id"])
    op.create_index("ix_zero_review_log_store_id", "zero_review_log", ["store_id"])
    op.create_index("ix_zero_review_log_period_start", "zero_review_log", ["period_start"])
    op.create_index("ix_zero_review_log_created_at", "zero_review_log", ["created_at"])
    # append-only: the log can be written but never changed or removed (a store deleted later only blanks store_id through its own foreign key)
    op.execute("""
        CREATE OR REPLACE FUNCTION zero_review_log_immutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'zero_review_log is append-only';
            END IF;
            IF NEW.store_id IS NULL AND OLD.store_id IS NOT NULL
               AND (to_jsonb(NEW) - 'store_id') = (to_jsonb(OLD) - 'store_id') THEN
                RETURN NEW;                      -- the foreign key's SET NULL when a store is deleted
            END IF;
            RAISE EXCEPTION 'zero_review_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER zero_review_log_no_change BEFORE UPDATE OR DELETE ON zero_review_log FOR EACH ROW EXECUTE FUNCTION zero_review_log_immutable()")



def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS zero_review_log_no_change ON zero_review_log")
    op.execute("DROP FUNCTION IF EXISTS zero_review_log_immutable()")
    op.drop_table("zero_review_log")
    op.drop_table("zero_review")
