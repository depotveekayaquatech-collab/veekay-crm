"""Nothing valuable is ever lost: every deleted row is copied to deleted_rows first, and every change to an order entry is kept

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-19

A BEFORE DELETE trigger on each protected table copies the whole row (as JSON) into `deleted_rows`, whatever deleted it: the app, a
developer tool, a cascade from a deleted store, or SQL typed by hand. The copy can be put back (see order_audit / deleted_data_service).
For order entries an AFTER UPDATE trigger also keeps the old and new number in `order_entry_changes`, so an overwrite is never silent.
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# Everything the business would be sorry to lose. Not users (password hashes) or sessions / caches.
PROTECTED = [
    "order_entries", "stores", "store_caps", "store_vendor_periods", "vendor_rates",
    "cash_purchases", "cash_adjustments", "cash_sync_records",
    "compliance_documents", "compliance_document_versions", "test_reports",
    "tickets", "ticket_comments", "bottles", "bottle_scans",
    "external_accounts", "external_account_stores",
    "attendance_records", "leave_requests", "employee_salaries", "payroll_day_marks", "payslips", "audit_logs",
]


def upgrade() -> None:
    op.execute("""
        CREATE TABLE deleted_rows (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name text NOT NULL,
            row_id text,
            data jsonb NOT NULL,
            deleted_at timestamptz NOT NULL DEFAULT now(),
            restored_at timestamptz
        )
    """)
    op.execute("CREATE INDEX ix_deleted_rows_table_time ON deleted_rows (table_name, deleted_at DESC)")
    op.execute("CREATE INDEX ix_deleted_rows_row ON deleted_rows (table_name, row_id)")
    op.execute("""
        CREATE FUNCTION keep_deleted_row() RETURNS trigger AS $$
        BEGIN
            INSERT INTO deleted_rows (table_name, row_id, data) VALUES (TG_TABLE_NAME, to_jsonb(OLD) ->> 'id', to_jsonb(OLD));
            RETURN OLD;
        END
        $$ LANGUAGE plpgsql
    """)
    for t in PROTECTED:
        op.execute(f"CREATE TRIGGER trg_keep_deleted BEFORE DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION keep_deleted_row()")

    op.execute("""
        CREATE TABLE order_entry_changes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_id uuid NOT NULL,
            store_id uuid NOT NULL,
            order_date date NOT NULL,
            old_count integer, new_count integer,
            old_cash_adjustment integer, new_cash_adjustment integer,
            old_source text, new_source text,
            changed_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_order_entry_changes_entry ON order_entry_changes (entry_id, changed_at DESC)")
    op.execute("CREATE INDEX ix_order_entry_changes_store_date ON order_entry_changes (store_id, order_date)")
    op.execute("""
        CREATE FUNCTION keep_order_entry_change() RETURNS trigger AS $$
        BEGIN
            IF OLD.bottle_count IS DISTINCT FROM NEW.bottle_count
               OR OLD.cash_adjustment IS DISTINCT FROM NEW.cash_adjustment
               OR OLD.source IS DISTINCT FROM NEW.source THEN
                INSERT INTO order_entry_changes (entry_id, store_id, order_date, old_count, new_count,
                                                 old_cash_adjustment, new_cash_adjustment, old_source, new_source)
                VALUES (OLD.id, OLD.store_id, OLD.order_date, OLD.bottle_count, NEW.bottle_count,
                        OLD.cash_adjustment, NEW.cash_adjustment, OLD.source, NEW.source);
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER trg_order_entry_changes AFTER UPDATE ON order_entries FOR EACH ROW EXECUTE FUNCTION keep_order_entry_change()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_order_entry_changes ON order_entries")
    op.execute("DROP FUNCTION IF EXISTS keep_order_entry_change()")
    op.execute("DROP TABLE IF EXISTS order_entry_changes")
    for t in PROTECTED:
        op.execute(f"DROP TRIGGER IF EXISTS trg_keep_deleted ON {t}")
    op.execute("DROP FUNCTION IF EXISTS keep_deleted_row()")
    op.execute("DROP TABLE IF EXISTS deleted_rows")
