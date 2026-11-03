"""Vendor payments fed from Busy 21: vendors, ledger entries, sync log, unmatched rows

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-03

Four new tables (plus vendor-code aliases); nothing existing is touched. `vendor_code` is the only link to Busy data, so a trigger refuses any
change to it after the vendor is created. The two permissions (vendorpay.view / vendorpay.manage) are computed per request like zero.*, so no rows are
inserted into `permissions` here.
"""
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE busy_vendors (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code varchar(32) NOT NULL,
            name varchar(160) NOT NULL,
            city varchar(80),
            opening_balance numeric(14,2) NOT NULL DEFAULT 0,
            opening_date date,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_busy_vendors_code UNIQUE (vendor_code),
            CONSTRAINT ck_busy_vendors_code_not_blank CHECK (btrim(vendor_code) <> ''),
            CONSTRAINT ck_busy_vendors_opening_first_of_month CHECK (opening_date IS NULL OR extract(day FROM opening_date) = 1)
        )
    """)
    op.execute("""
        CREATE FUNCTION busy_vendor_code_immutable() RETURNS trigger AS $$
        BEGIN
            IF NEW.vendor_code <> OLD.vendor_code THEN
                RAISE EXCEPTION 'vendor_code cannot be changed after the vendor is created';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER trg_busy_vendor_code_immutable BEFORE UPDATE ON busy_vendors FOR EACH ROW EXECUTE FUNCTION busy_vendor_code_immutable()")

    op.execute("""
        CREATE TABLE busy_vendor_aliases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alias_code varchar(32) NOT NULL,
            vendor_code varchar(32) NOT NULL REFERENCES busy_vendors(vendor_code) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_busy_vendor_aliases_alias UNIQUE (alias_code)
        )
    """)
    op.execute("CREATE INDEX ix_busy_vendor_aliases_vendor_code ON busy_vendor_aliases (vendor_code)")

    op.execute("""
        CREATE TABLE busy_ledger_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            vendor_code varchar(32) NOT NULL REFERENCES busy_vendors(vendor_code) ON DELETE RESTRICT,
            entry_date date NOT NULL,
            entry_type varchar(8) NOT NULL,
            amount numeric(14,2) NOT NULL,
            voucher_no varchar(64) NOT NULL,
            narration text,
            source varchar(8) NOT NULL,
            synced_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_busy_ledger_key UNIQUE (vendor_code, voucher_no, entry_type),
            CONSTRAINT ck_busy_ledger_amount_positive CHECK (amount > 0),
            CONSTRAINT ck_busy_ledger_type CHECK (entry_type IN ('BILL','PAYMENT')),
            CONSTRAINT ck_busy_ledger_source CHECK (source IN ('API','CSV','MANUAL'))
        )
    """)
    op.execute("CREATE INDEX ix_busy_ledger_vendor_date ON busy_ledger_entries (vendor_code, entry_date)")
    op.execute("CREATE INDEX ix_busy_ledger_entries_entry_date ON busy_ledger_entries (entry_date)")

    op.execute("""
        CREATE TABLE busy_sync_logs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at timestamptz NOT NULL,
            finished_at timestamptz,
            source varchar(8) NOT NULL,
            mode varchar(16),
            period_from date,
            period_to date,
            triggered_by varchar(120),
            rows_received integer NOT NULL DEFAULT 0,
            rows_inserted integer NOT NULL DEFAULT 0,
            rows_updated integer NOT NULL DEFAULT 0,
            rows_unchanged integer NOT NULL DEFAULT 0,
            rows_deleted integer NOT NULL DEFAULT 0,
            rows_unmatched integer NOT NULL DEFAULT 0,
            rows_rejected integer NOT NULL DEFAULT 0,
            status varchar(8) NOT NULL,
            error_message text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_busy_sync_logs_finished_at ON busy_sync_logs (finished_at)")
    op.execute("CREATE INDEX ix_busy_sync_logs_status ON busy_sync_logs (status)")

    op.execute("""
        CREATE TABLE busy_unmatched_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            dedupe_key varchar(64) NOT NULL,
            vendor_code varchar(32),
            account_name varchar(300) NOT NULL DEFAULT '',
            entry_date date NOT NULL,
            entry_type varchar(8) NOT NULL,
            amount numeric(14,2) NOT NULL,
            voucher_no varchar(64) NOT NULL,
            narration text,
            source varchar(8) NOT NULL,
            raw jsonb NOT NULL,
            sync_log_id uuid REFERENCES busy_sync_logs(id) ON DELETE SET NULL,
            status varchar(8) NOT NULL DEFAULT 'OPEN',
            resolved_at timestamptz,
            resolved_vendor_code varchar(32),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_busy_unmatched_dedupe UNIQUE (dedupe_key)
        )
    """)
    op.execute("CREATE INDEX ix_busy_unmatched_status_code ON busy_unmatched_entries (status, vendor_code)")


def downgrade() -> None:
    for table in ("busy_unmatched_entries", "busy_sync_logs", "busy_ledger_entries", "busy_vendor_aliases", "busy_vendors"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION busy_vendor_code_immutable()")
