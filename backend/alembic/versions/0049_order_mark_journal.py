"""an immutable journal of every number an employee tries to mark, saved or not

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-22

When a mark was refused (the day already held an imported number, the request failed half way...) the employee's number used to vanish:
only the error was shown. Now every attempt is written here, in its own transaction, whatever happens to the mark itself. The core
columns can never be changed or deleted (database triggers); only the resolution columns are filled in when an admin deals with it.
"""
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE order_mark_journal (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at timestamptz NOT NULL DEFAULT now(),
            organization_id uuid NOT NULL,
            user_id uuid,
            store_id uuid NOT NULL,
            order_date date NOT NULL,
            bottle_count integer,
            action text NOT NULL DEFAULT 'mark',
            outcome text NOT NULL,
            reason text,
            request_key text,
            client text,
            resolved_at timestamptz,
            resolved_by_user_id uuid,
            resolution text
        )
    """)
    op.execute("CREATE INDEX ix_order_mark_journal_open ON order_mark_journal (organization_id, outcome, resolved_at, created_at DESC)")
    op.execute("CREATE INDEX ix_order_mark_journal_store ON order_mark_journal (store_id, order_date)")
    op.execute("""
        CREATE FUNCTION order_mark_journal_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'order_mark_journal rows cannot be deleted';
            END IF;
            IF (NEW.created_at, NEW.organization_id, NEW.user_id, NEW.store_id, NEW.order_date, NEW.bottle_count, NEW.action, NEW.outcome, NEW.reason, NEW.request_key, NEW.client)
               IS DISTINCT FROM
               (OLD.created_at, OLD.organization_id, OLD.user_id, OLD.store_id, OLD.order_date, OLD.bottle_count, OLD.action, OLD.outcome, OLD.reason, OLD.request_key, OLD.client) THEN
                RAISE EXCEPTION 'order_mark_journal rows cannot be changed (only resolved)';
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER trg_order_mark_journal_guard BEFORE UPDATE OR DELETE ON order_mark_journal FOR EACH ROW EXECUTE FUNCTION order_mark_journal_guard()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_order_mark_journal_guard ON order_mark_journal")
    op.execute("DROP FUNCTION IF EXISTS order_mark_journal_guard()")
    op.execute("DROP TABLE IF EXISTS order_mark_journal")
