"""entry verification workflow: Submitted (L1) -> Verified by Team Lead (L2) -> Reviewed by Reviewer (L3), enforced inside the database

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-24

order_entries.bottle_count stays the ONE number every report reads, and it is always the final one: the L1 number until somebody senior changes it, then
the Team Lead's (verified), then the Reviewer's (reviewed). Earlier values live only in order_entry_events (append-only), so reports never see an
intermediate version and the history is never overwritten.

The state is decided by the database, from who changed the number, so every writer is covered (mark, correction, import, cash tools, SQL by hand):

  * a NEW entry starts as `submitted`, unless a more senior person created it (a Team Lead's own entry is `verified_l2`, an administrator's / reviewer's
    is `reviewed_l3`);
  * a changed number moves the entry to the state of whoever changed it: Team Lead -> verified_l2 (only while it was still `submitted`),
    reviewer / administrator -> reviewed_l3, anyone else (the contributor, or no known actor) -> back to `submitted`;
  * without a number change the state may only move forward: submitted -> verified_l2 (Team Lead or above), -> reviewed_l3 (reviewer or above).
    This is the "Reviewer shortcut": a reviewer may finalise a `submitted` entry directly, and the Team Lead is not asked afterwards.

A reviewer can also ask the Team Lead to check an entry (check_requested_*): an open request, cleared by the next verification or change.
Every transition appends an event (VERIFIED_L2, REVIEWED_L3, CHECK_REQUESTED, STATUS_CHANGED) in the same transaction.

Existing entries: all start as `submitted` (nobody has verified them; the column default is a constant so adding it rewrites nothing). Entries a reviewer
had already marked `reviewed` under 0052 become `reviewed_l3`.

Forward-only: the triggers below read the new columns, so this migration is not downgraded.
"""
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

TRACKED_NEW = """jsonb_build_object('store_id', NEW.store_id, 'order_date', NEW.order_date, 'bottle_count', NEW.bottle_count,
    'cash_adjustment', NEW.cash_adjustment, 'source', NEW.source, 'review_status', NEW.review_status,
    'verification_status', NEW.verification_status)"""
TRACKED_OLD = TRACKED_NEW.replace("NEW.", "OLD.")


def upgrade() -> None:
    op.execute("""
        ALTER TABLE order_entries
            ADD COLUMN verification_status text NOT NULL DEFAULT 'submitted',
            ADD COLUMN verified_by_user_id uuid,
            ADD COLUMN verified_at timestamptz,
            ADD COLUMN l3_reviewed_by_user_id uuid,
            ADD COLUMN l3_reviewed_at timestamptz,
            ADD COLUMN check_requested_by_user_id uuid,
            ADD COLUMN check_requested_at timestamptz,
            ADD COLUMN check_request_note text
    """)
    op.execute("ALTER TABLE order_entries ADD CONSTRAINT ck_order_entries_verification_status CHECK (verification_status IN ('submitted','verified_l2','reviewed_l3'))")
    # Backfill BEFORE the new trigger functions exist: the old triggers do not know these columns, so this writes no history event.
    op.execute("""
        UPDATE order_entries SET verification_status = 'reviewed_l3', l3_reviewed_by_user_id = reviewed_by_user_id, l3_reviewed_at = reviewed_at
         WHERE review_status = 'reviewed'
    """)
    op.execute("CREATE INDEX ix_order_entries_verification ON order_entries (organization_id, verification_status, order_date DESC)")
    op.execute("CREATE INDEX ix_order_entries_check_requested ON order_entries (organization_id, check_requested_at DESC) WHERE check_requested_at IS NOT NULL")

    op.execute("""
        CREATE FUNCTION entry_role_rank(r text) RETURNS integer LANGUAGE sql IMMUTABLE AS $$
            SELECT CASE
                WHEN r IN ('developer', 'administrator') THEN 4
                WHEN r IN ('entry_reviewer', 'custom_admin') THEN 3
                WHEN r = 'team_lead' THEN 2
                WHEN r IN ('entry_contributor', 'accountant', 'partner') THEN 1
                ELSE 0 END
        $$
    """)

    # ------------------------------------------------------------------ stamp (INSERT): the starting state follows the creator's level
    op.execute("""
        CREATE OR REPLACE FUNCTION order_entries_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            keep boolean := entry_ctx('keep_creator') = 'on' AND NEW.created_by_user_id IS NOT NULL;
            rk integer;
        BEGIN
            IF keep THEN
                NULL;                                         -- a restore of a deleted entry carries its original creator back
            ELSIF actor IS NOT NULL THEN
                NEW.created_by_user_id := actor;
                NEW.created_by_role := entry_actor_role(actor);
                SELECT full_name, employee_code INTO NEW.created_by_name, NEW.created_by_code FROM users WHERE id = actor;
                NEW.creator_verified := true;
                NEW.created_at := clock_timestamp();           -- the server's clock, never the phone's
            ELSE
                NEW.created_by_user_id := NULL;                -- written with no authenticated actor (direct SQL, script): never guessed
                NEW.created_by_role := NULL; NEW.created_by_name := NULL; NEW.created_by_code := NULL;
                NEW.creator_verified := false;
            END IF;
            IF NOT keep THEN
                NEW.created_via := coalesce(entry_ctx('source'), CASE WHEN actor IS NULL THEN 'no_actor' ELSE 'unknown' END);
                NEW.request_id := coalesce(NEW.request_id, entry_ctx('request_key'));
                NEW.client_submitted_at := coalesce(NEW.client_submitted_at, nullif(entry_ctx('client_time'), '')::timestamptz);
                NEW.source_app := coalesce(NEW.source_app, entry_ctx('client'));
            END IF;
            NEW.version := 1;
            NEW.review_status := 'none';
            NEW.verified_by_user_id := NULL; NEW.verified_at := NULL; NEW.l3_reviewed_by_user_id := NULL; NEW.l3_reviewed_at := NULL;
            NEW.check_requested_by_user_id := NULL; NEW.check_requested_at := NULL; NEW.check_request_note := NULL;
            rk := entry_role_rank(NEW.created_by_role);
            IF rk >= 3 THEN
                NEW.verification_status := 'reviewed_l3'; NEW.l3_reviewed_by_user_id := NEW.created_by_user_id; NEW.l3_reviewed_at := clock_timestamp();
            ELSIF rk = 2 THEN
                NEW.verification_status := 'verified_l2'; NEW.verified_by_user_id := NEW.created_by_user_id; NEW.verified_at := clock_timestamp();
            ELSE
                NEW.verification_status := 'submitted';
            END IF;
            RETURN NEW;
        END
        $$
    """)

    # ------------------------------------------------------------------ guard (UPDATE): immutability + the state machine
    op.execute("""
        CREATE OR REPLACE FUNCTION order_entries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            arole text := CASE WHEN entry_ctx_uuid('actor_id') IS NULL THEN NULL ELSE entry_actor_role(entry_ctx_uuid('actor_id')) END;
            rk integer := entry_role_rank(arole);
            changed boolean;
            number_changed boolean;
        BEGIN
            IF (NEW.id, NEW.created_by_user_id, NEW.created_by_role, NEW.created_by_name, NEW.created_by_code, NEW.creator_verified,
                NEW.created_via, NEW.request_id, NEW.created_at, NEW.client_submitted_at)
               IS DISTINCT FROM
               (OLD.id, OLD.created_by_user_id, OLD.created_by_role, OLD.created_by_name, OLD.created_by_code, OLD.creator_verified,
                OLD.created_via, OLD.request_id, OLD.created_at, OLD.client_submitted_at) THEN
                RAISE EXCEPTION 'order_entries: the creator, creation time and identity of an entry can never be changed';
            END IF;
            changed := (NEW.bottle_count, NEW.cash_adjustment, NEW.source, NEW.store_id, NEW.order_date)
                       IS DISTINCT FROM (OLD.bottle_count, OLD.cash_adjustment, OLD.source, OLD.store_id, OLD.order_date);
            number_changed := (NEW.bottle_count, NEW.cash_adjustment) IS DISTINCT FROM (OLD.bottle_count, OLD.cash_adjustment);
            IF changed THEN
                NEW.version := OLD.version + 1;
                NEW.last_modified_by_user_id := actor;
                NEW.last_modified_by_role := arole;
                NEW.last_modified_at := clock_timestamp();
            ELSE
                NEW.version := OLD.version;
            END IF;
            IF NEW.review_status IS DISTINCT FROM OLD.review_status THEN
                NEW.reviewed_by_user_id := actor;
                NEW.reviewed_at := clock_timestamp();
            END IF;

            IF number_changed THEN
                -- the number changed: whoever changed it decides the state
                IF rk >= 3 THEN
                    NEW.verification_status := 'reviewed_l3'; NEW.l3_reviewed_by_user_id := actor; NEW.l3_reviewed_at := clock_timestamp();
                ELSIF rk = 2 THEN
                    IF OLD.verification_status <> 'submitted' THEN
                        RAISE EXCEPTION 'order_entries: a Team Lead can only change an entry that is still Submitted';
                    END IF;
                    NEW.verification_status := 'verified_l2'; NEW.verified_by_user_id := actor; NEW.verified_at := clock_timestamp();
                ELSE
                    NEW.verification_status := 'submitted';
                    NEW.verified_by_user_id := NULL; NEW.verified_at := NULL; NEW.l3_reviewed_by_user_id := NULL; NEW.l3_reviewed_at := NULL;
                END IF;
                NEW.check_requested_by_user_id := NULL; NEW.check_requested_at := NULL; NEW.check_request_note := NULL;
            ELSIF NEW.verification_status IS DISTINCT FROM OLD.verification_status THEN
                IF NEW.verification_status = 'verified_l2' THEN
                    IF OLD.verification_status <> 'submitted' OR rk < 2 THEN
                        RAISE EXCEPTION 'order_entries: only a Team Lead (or above) can verify an entry that is Submitted';
                    END IF;
                    NEW.verified_by_user_id := actor; NEW.verified_at := clock_timestamp();
                ELSIF NEW.verification_status = 'reviewed_l3' THEN
                    IF rk < 3 THEN
                        RAISE EXCEPTION 'order_entries: only a Reviewer (or above) can finalise an entry';
                    END IF;
                    NEW.l3_reviewed_by_user_id := actor; NEW.l3_reviewed_at := clock_timestamp();
                ELSE
                    RAISE EXCEPTION 'order_entries: a verified or reviewed entry cannot be moved back to Submitted without changing its number';
                END IF;
                NEW.check_requested_by_user_id := NULL; NEW.check_requested_at := NULL; NEW.check_request_note := NULL;
            ELSIF NEW.check_requested_at IS NOT NULL AND NEW.check_requested_at IS DISTINCT FROM OLD.check_requested_at THEN
                IF rk < 3 THEN
                    RAISE EXCEPTION 'order_entries: only a Reviewer (or above) can ask for a check';
                END IF;
                IF NEW.verification_status <> 'submitted' THEN
                    RAISE EXCEPTION 'order_entries: a check can only be requested for an entry that is still Submitted';
                END IF;
                NEW.check_requested_by_user_id := actor;
            END IF;
            RETURN NEW;
        END
        $$
    """)

    # ------------------------------------------------------------------ audit (AFTER): the new transitions append their own events
    op.execute(f"""
        CREATE OR REPLACE FUNCTION order_entries_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            o jsonb := '{{}}'::jsonb;
            n jsonb := '{{}}'::jsonb;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id, coalesce(entry_ctx('event_type'), 'CREATED'), NULL,
                                           {TRACKED_NEW}, NEW.version, actor, entry_ctx('reason'), entry_ctx('comment'));
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                PERFORM entry_append_event(OLD.id, OLD.store_id, OLD.organization_id, 'CLEARED', {TRACKED_OLD}, NULL, OLD.version,
                                           actor, entry_ctx('reason'), entry_ctx('comment'));
                RETURN OLD;
            END IF;
            -- UPDATE: only what changed
            IF OLD.bottle_count IS DISTINCT FROM NEW.bottle_count THEN
                o := o || jsonb_build_object('bottle_count', OLD.bottle_count); n := n || jsonb_build_object('bottle_count', NEW.bottle_count);
            END IF;
            IF OLD.cash_adjustment IS DISTINCT FROM NEW.cash_adjustment THEN
                o := o || jsonb_build_object('cash_adjustment', OLD.cash_adjustment); n := n || jsonb_build_object('cash_adjustment', NEW.cash_adjustment);
            END IF;
            IF OLD.source IS DISTINCT FROM NEW.source THEN
                o := o || jsonb_build_object('source', OLD.source); n := n || jsonb_build_object('source', NEW.source);
            END IF;
            IF OLD.store_id IS DISTINCT FROM NEW.store_id THEN
                o := o || jsonb_build_object('store_id', OLD.store_id); n := n || jsonb_build_object('store_id', NEW.store_id);
            END IF;
            IF OLD.order_date IS DISTINCT FROM NEW.order_date THEN
                o := o || jsonb_build_object('order_date', OLD.order_date); n := n || jsonb_build_object('order_date', NEW.order_date);
            END IF;
            IF n <> '{{}}'::jsonb THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id, coalesce(entry_ctx('event_type'), 'EDITED'), o, n,
                                           NEW.version, actor, entry_ctx('reason'), entry_ctx('comment'));
            END IF;
            IF OLD.review_status IS DISTINCT FROM NEW.review_status THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id,
                    CASE NEW.review_status WHEN 'reviewed' THEN 'REVIEWED' WHEN 'flagged' THEN 'FLAGGED'
                                           WHEN 'needs_correction' THEN 'NEEDS_CORRECTION' ELSE 'STATUS_CHANGED' END,
                    jsonb_build_object('review_status', OLD.review_status), jsonb_build_object('review_status', NEW.review_status),
                    NEW.version, actor, entry_ctx('reason'), entry_ctx('comment'));
            END IF;
            IF OLD.verification_status IS DISTINCT FROM NEW.verification_status THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id,
                    CASE NEW.verification_status WHEN 'verified_l2' THEN 'VERIFIED_L2' WHEN 'reviewed_l3' THEN 'REVIEWED_L3' ELSE 'STATUS_CHANGED' END,
                    jsonb_build_object('verification_status', OLD.verification_status), jsonb_build_object('verification_status', NEW.verification_status),
                    NEW.version, actor, entry_ctx('reason'), entry_ctx('comment'));
            END IF;
            IF NEW.check_requested_at IS NOT NULL AND NEW.check_requested_at IS DISTINCT FROM OLD.check_requested_at THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id, 'CHECK_REQUESTED', NULL,
                    jsonb_build_object('verification_status', NEW.verification_status), NEW.version, actor, entry_ctx('reason'), NEW.check_request_note);
            END IF;
            RETURN NEW;
        END
        $$
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0053 is forward-only: the entry triggers read its columns, so dropping them would break every write to order_entries. "
        "Restore a database backup instead."
    )
