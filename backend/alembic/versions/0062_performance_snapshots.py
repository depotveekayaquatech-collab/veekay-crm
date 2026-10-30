"""Performance report snapshots: what was reported, kept forever, and never rewritten

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-30

The performance report is recounted from the entries on every look (by design), so a figure printed yesterday can never be re-read from the data alone:
an entry added late, an entry cleared, a store moved to someone else all change it (a holiday does not: holidays are attendance's business). A snapshot records what a report SAID at the moment it was
produced: the per-employee figures, the judged days it used, the store list behind each employee, and the exact instant of its data
(`generated_at`), which is enough to rebuild the figures from `order_entries` + `deleted_rows` and check them (see performance_reconciliation_service).

Append-only, like the entry history: the database refuses UPDATE, DELETE and TRUNCATE (the `append_only_guard` of migration 0052). A report that needs
correcting is never edited: a NEW snapshot is written with `revision_of` pointing at the original and a `revision_reason`. Nothing here changes an
existing table or deletes anything.
"""
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE performance_snapshots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            partner_slug text NOT NULL,
            month date NOT NULL,
            as_of date,                                   -- last day judged (null when no day of the month had finished)
            generated_at timestamptz NOT NULL,            -- the instant of the data: the transaction's snapshot time
            generated_by_user_id uuid,                    -- no FK on purpose: identity outlives the account
            generated_by_name text,
            source text NOT NULL,                         -- 'manual' | 'scheduled' | 'report' (someone copied the report to send it)
            definition_version text NOT NULL,
            judged_days jsonb NOT NULL,                   -- ["2026-10-01", ...] the days that counted
            employees jsonb NOT NULL,                     -- one object per employee: the figures exactly as reported
            scopes jsonb NOT NULL,                        -- {employee_id: [store ids]} the stores behind each employee's figures
            summary jsonb NOT NULL,
            report_text text,                             -- the literal text that was copied, when source = 'report'
            content_hash text NOT NULL,
            revision_of uuid REFERENCES performance_snapshots(id),
            revision_reason text,
            CONSTRAINT ck_perf_snapshot_revision CHECK (revision_of IS NULL OR coalesce(revision_reason, '') <> '')
        )
    """)
    op.execute("CREATE INDEX ix_perf_snapshots_lookup ON performance_snapshots (organization_id, partner_slug, month, generated_at DESC)")
    op.execute("CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON performance_snapshots FOR EACH ROW EXECUTE FUNCTION append_only_guard()")
    op.execute("CREATE TRIGGER trg_append_only_truncate BEFORE TRUNCATE ON performance_snapshots FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard()")


def downgrade() -> None:
    # Only for a database that never received a snapshot: the table is append-only, so it must be emptied by a DBA on purpose before it can go.
    op.execute("DROP TABLE performance_snapshots")
