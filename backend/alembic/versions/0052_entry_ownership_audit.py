"""entry ownership + an append-only, hash-chained audit trail enforced INSIDE the database

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-23

Why in the database: entries are written from many places (employee marks, admin corrections, sheet imports, restores, cash tools, repair
tools, SQL typed by hand). A trigger covers all of them, in the same transaction as the change, and cannot be forgotten by a new code path.

  * order_entries gets an IMMUTABLE creator (user id + name / code / role snapshot), a verified flag, a version number, last modifier,
    review state, the client's own submit time and the idempotency key. The creator is whoever the server authenticated for the request
    (session setting `app.actor_id`); nothing the phone sends can set it. Writes with no known actor are recorded as unverified.
  * order_entry_events is the append-only history: CREATED / EDITED / CLEARED / REVIEWED / FLAGGED ... with previous and new values, the
    actor's identity and role AT THAT TIME, the reason, request id and source. UPDATE / DELETE / TRUNCATE are refused by triggers. Every event
    carries a hash of the previous event of the same entry, so an after-the-fact change is detectable (entry_verify_chain).
  * security_events is a separate append-only log for refused / sensitive actions (cross-scope attempts, role changes).
  * users.reports_to_user_id gives the Team Lead -> team relationship; roles team_lead and entry_reviewer + their permissions.

Existing entries: nothing is deleted or renamed. A creator is filled in ONLY where the activity log proves it (the latest `order.marked`
event for that store and date was by the entry's current marker and the entry is still an employee entry); every other entry stays
`creator_verified = false` with no creator, and keeps its old marked_by_user_id as the "last recorded marker" to investigate. Each existing
entry gets a BASELINE event so the history starts from a known state.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

TRACKED_JSON_NEW = """jsonb_build_object('store_id', NEW.store_id, 'order_date', NEW.order_date, 'bottle_count', NEW.bottle_count,
    'cash_adjustment', NEW.cash_adjustment, 'source', NEW.source, 'review_status', NEW.review_status)"""
TRACKED_JSON_OLD = TRACKED_JSON_NEW.replace("NEW.", "OLD.")


def upgrade() -> None:
    # ------------------------------------------------------------------ columns
    op.execute("""
        ALTER TABLE order_entries
            ADD COLUMN created_by_user_id uuid,
            ADD COLUMN created_by_role text,
            ADD COLUMN created_by_name text,
            ADD COLUMN created_by_code text,
            ADD COLUMN creator_verified boolean NOT NULL DEFAULT false,
            ADD COLUMN created_via text,
            ADD COLUMN version integer NOT NULL DEFAULT 1,
            ADD COLUMN last_modified_by_user_id uuid,
            ADD COLUMN last_modified_by_role text,
            ADD COLUMN last_modified_at timestamptz,
            ADD COLUMN review_status text NOT NULL DEFAULT 'none',
            ADD COLUMN reviewed_by_user_id uuid,
            ADD COLUMN reviewed_at timestamptz,
            ADD COLUMN client_submitted_at timestamptz,
            ADD COLUMN request_id text,
            ADD COLUMN source_app text
    """)
    op.execute("ALTER TABLE order_entries ADD CONSTRAINT ck_order_entries_review_status CHECK (review_status IN ('none','reviewed','flagged','needs_correction'))")
    op.execute("CREATE INDEX ix_order_entries_creator_date ON order_entries (created_by_user_id, order_date)")
    op.execute("CREATE INDEX ix_order_entries_unverified ON order_entries (organization_id, order_date) WHERE creator_verified = false")
    op.execute("CREATE INDEX ix_order_entries_review ON order_entries (organization_id, review_status) WHERE review_status <> 'none'")
    op.execute(
        "CREATE UNIQUE INDEX uq_order_entries_creator_request ON order_entries (created_by_user_id, request_id) "
        "WHERE request_id IS NOT NULL AND created_by_user_id IS NOT NULL"
    )
    op.execute("ALTER TABLE users ADD COLUMN reports_to_user_id uuid REFERENCES users(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX ix_users_reports_to ON users (reports_to_user_id) WHERE reports_to_user_id IS NOT NULL")

    # ------------------------------------------------------------------ append-only tables
    op.execute("""
        CREATE TABLE order_entry_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            entry_id uuid NOT NULL,
            store_id uuid,
            organization_id uuid,
            event_type text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            actor_user_id uuid,
            actor_known boolean NOT NULL DEFAULT false,
            actor_name text,
            actor_code text,
            actor_role text,
            old_values jsonb,
            new_values jsonb,
            reason text,
            comment text,
            request_id text,
            source text,
            entry_version integer,
            prev_hash text,
            hash text NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_oee_entry ON order_entry_events (entry_id, seq)")
    op.execute("CREATE INDEX ix_oee_store_time ON order_entry_events (store_id, created_at DESC)")
    op.execute("CREATE INDEX ix_oee_actor_time ON order_entry_events (actor_user_id, created_at DESC)")
    op.execute("CREATE INDEX ix_oee_org_time ON order_entry_events (organization_id, created_at DESC)")
    op.execute("CREATE INDEX ix_oee_type ON order_entry_events (event_type, created_at DESC)")

    op.execute("""
        CREATE TABLE security_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            organization_id uuid,
            actor_user_id uuid,
            actor_name text,
            actor_code text,
            actor_role text,
            event_type text NOT NULL,
            target_type text,
            target_id text,
            detail jsonb,
            request_id text,
            ip text
        )
    """)
    op.execute("CREATE INDEX ix_security_events_time ON security_events (organization_id, created_at DESC)")
    op.execute("CREATE INDEX ix_security_events_type ON security_events (event_type, created_at DESC)")

    op.execute("""
        CREATE FUNCTION append_only_guard() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: rows cannot be changed, deleted or truncated', TG_TABLE_NAME;
        END
        $$ LANGUAGE plpgsql
    """)
    for t in ("order_entry_events", "security_events"):
        op.execute(f"CREATE TRIGGER trg_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION append_only_guard()")
        op.execute(f"CREATE TRIGGER trg_append_only_truncate BEFORE TRUNCATE ON {t} FOR EACH STATEMENT EXECUTE FUNCTION append_only_guard()")

    # ------------------------------------------------------------------ helpers
    op.execute("""
        CREATE FUNCTION entry_ctx(k text) RETURNS text LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.' || k, true), '') $$
    """)
    op.execute("""
        CREATE FUNCTION entry_ctx_uuid(k text) RETURNS uuid LANGUAGE plpgsql STABLE AS $$
        DECLARE v text := entry_ctx(k);
        BEGIN
            IF v IS NULL THEN RETURN NULL; END IF;
            RETURN v::uuid;
        EXCEPTION WHEN others THEN
            RETURN NULL;
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION entry_actor_role(uid uuid) RETURNS text LANGUAGE sql STABLE AS $$
            SELECT CASE
                WHEN bool_or(r.code = 'developer') THEN 'developer'
                WHEN bool_or(r.code = 'admin') THEN 'administrator'
                WHEN bool_or(r.code = 'manager') THEN 'custom_admin'
                WHEN bool_or(r.code = 'entry_reviewer') THEN 'entry_reviewer'
                WHEN bool_or(r.code = 'team_lead') THEN 'team_lead'
                WHEN bool_or(r.code = 'accountant') THEN 'accountant'
                WHEN bool_or(r.code = 'partner') THEN 'partner'
                WHEN bool_or(r.code = 'employee') THEN 'entry_contributor'
                ELSE 'unknown' END
            FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = uid
        $$
    """)
    op.execute("""
        CREATE FUNCTION entry_event_hash(prev text, entry uuid, etype text, actor uuid, ts timestamptz, o jsonb, n jsonb,
                                         why text, note text, ver integer) RETURNS text LANGUAGE sql IMMUTABLE AS $$
            SELECT encode(sha256(convert_to(
                coalesce(prev, '') || concat_ws('|', entry::text, etype, coalesce(actor::text, ''),
                    to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'), coalesce(o::text, ''), coalesce(n::text, ''),
                    coalesce(why, ''), coalesce(note, ''), coalesce(ver::text, '')), 'UTF8')), 'hex')
        $$
    """)
    op.execute("""
        CREATE FUNCTION entry_append_event(p_entry uuid, p_store uuid, p_org uuid, p_type text, p_old jsonb, p_new jsonb, p_version integer,
                                           p_actor uuid, p_reason text, p_comment text) RETURNS void LANGUAGE plpgsql AS $$
        DECLARE
            prev text; a_name text; a_code text; a_role text; ts timestamptz := clock_timestamp();
        BEGIN
            IF p_actor IS NOT NULL THEN
                SELECT full_name, employee_code INTO a_name, a_code FROM users WHERE id = p_actor;
                a_role := entry_actor_role(p_actor);
            END IF;
            SELECT hash INTO prev FROM order_entry_events WHERE entry_id = p_entry ORDER BY seq DESC LIMIT 1;
            INSERT INTO order_entry_events (entry_id, store_id, organization_id, event_type, created_at, actor_user_id, actor_known, actor_name,
                                            actor_code, actor_role, old_values, new_values, reason, comment, request_id, source, entry_version,
                                            prev_hash, hash)
            VALUES (p_entry, p_store, p_org, p_type, ts, p_actor, p_actor IS NOT NULL, a_name, a_code, a_role, p_old, p_new, p_reason, p_comment,
                    entry_ctx('request_id'), entry_ctx('source'), p_version, prev,
                    entry_event_hash(prev, p_entry, p_type, p_actor, ts, p_old, p_new, p_reason, p_comment, p_version));
        END
        $$
    """)
    op.execute("""
        CREATE FUNCTION entry_verify_chain(p_entry uuid) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
        DECLARE r record; prev text := NULL;
        BEGIN
            FOR r IN SELECT * FROM order_entry_events WHERE entry_id = p_entry ORDER BY seq LOOP
                IF r.prev_hash IS DISTINCT FROM prev THEN RETURN false; END IF;
                IF r.hash <> entry_event_hash(prev, r.entry_id, r.event_type, r.actor_user_id, r.created_at, r.old_values, r.new_values,
                                              r.reason, r.comment, r.entry_version) THEN RETURN false; END IF;
                prev := r.hash;
            END LOOP;
            RETURN true;
        END
        $$
    """)

    # ------------------------------------------------------------------ roles + permissions
    bind = op.get_bind()
    perms = {
        "entries.team": "Team Lead: see and correct the entries of the people who report to you",
        "entries.audit": "Store Audit: search every entry and open its full history (Entry Reviewer, admin)",
        "entries.review": "Mark entries reviewed or flagged (Entry Reviewer, admin)",
    }
    for code, desc in perms.items():
        if not bind.execute(sa.text("SELECT 1 FROM permissions WHERE code = :c"), {"c": code}).first():
            bind.execute(sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, :c, :d)"), {"i": uuid.uuid4(), "c": code, "d": desc})
    for code, name, grants in (
        ("team_lead", "Team Lead", ["entries.team"]),
        ("entry_reviewer", "Entry Reviewer", ["entries.audit", "entries.review"]),
    ):
        if not bind.execute(sa.text("SELECT 1 FROM roles WHERE code = :c"), {"c": code}).first():
            bind.execute(sa.text("INSERT INTO roles (id, code, name, created_at, updated_at) VALUES (:i, :c, :n, now(), now())"),
                         {"i": uuid.uuid4(), "c": code, "n": name})
        for g in grants:
            bind.execute(sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                "SELECT r.id, p.id, now(), now() FROM roles r, permissions p WHERE r.code = :r AND p.code = :p ON CONFLICT DO NOTHING"
            ), {"r": code, "p": g})

    # ------------------------------------------------------------------ backfill (before the triggers exist)
    # A creator is proven only when the activity log's LATEST `order.marked` for this store+date is by the entry's current marker
    # and the entry is still an employee entry (nobody has re-written it since). Everything else stays unverified, never guessed.
    # Staged through typed, indexed temporary tables: one big statement that joined a text-keyed subquery to the entries ran for over ten minutes on
    # 300,000 entries (the planner nested-looped it). Stepwise it takes seconds.
    op.execute("""
        CREATE TEMP TABLE _last_mark ON COMMIT DROP AS
        SELECT DISTINCT ON (a.entity_id, a.metadata_json ->> 'order_date')
               a.entity_id::uuid AS store_id, (a.metadata_json ->> 'order_date')::date AS d, a.user_id
        FROM audit_logs a
        WHERE a.action = 'order.marked' AND a.user_id IS NOT NULL AND a.metadata_json ? 'order_date'
          AND a.entity_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
          AND a.metadata_json ->> 'order_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        ORDER BY a.entity_id, a.metadata_json ->> 'order_date', a.created_at DESC
    """)
    op.execute("CREATE INDEX ON _last_mark (store_id, d)")
    op.execute("ANALYZE _last_mark")
    op.execute("""
        CREATE TEMP TABLE _marker_identity ON COMMIT DROP AS
        SELECT u.id, u.full_name, u.employee_code, entry_actor_role(u.id) AS role
          FROM users u WHERE u.id IN (SELECT DISTINCT user_id FROM _last_mark)
    """)
    op.execute("CREATE UNIQUE INDEX ON _marker_identity (id)")
    op.execute("""
        UPDATE order_entries e
           SET created_by_user_id = i.id, creator_verified = true, created_via = 'verified_from_activity_log',
               created_by_name = i.full_name, created_by_code = i.employee_code, created_by_role = i.role
          FROM _last_mark m JOIN _marker_identity i ON i.id = m.user_id
         WHERE m.store_id = e.store_id AND m.d = e.order_date
           AND e.source = 'employee' AND e.marked_by_user_id = m.user_id
    """)
    op.execute("UPDATE order_entries SET created_via = 'legacy_unverified' WHERE creator_verified = false AND created_via IS NULL")
    op.execute(f"""
        INSERT INTO order_entry_events (entry_id, store_id, organization_id, event_type, created_at, actor_user_id, actor_known, actor_name,
                                        actor_code, actor_role, new_values, reason, entry_version, prev_hash, hash)
        SELECT e.id, e.store_id, e.organization_id, 'BASELINE', e.created_at, e.created_by_user_id, e.created_by_user_id IS NOT NULL,
               e.created_by_name, e.created_by_code, e.created_by_role, nv.j,
               CASE WHEN e.creator_verified THEN 'Existing entry; creator proven from the activity log'
                    ELSE 'Existing entry; creator NOT verified (last recorded marker kept in marked_by_user_id)' END,
               1, NULL,
               entry_event_hash(NULL, e.id, 'BASELINE', e.created_by_user_id, e.created_at, NULL, nv.j,
                                CASE WHEN e.creator_verified THEN 'Existing entry; creator proven from the activity log'
                                     ELSE 'Existing entry; creator NOT verified (last recorded marker kept in marked_by_user_id)' END, NULL, 1)
          FROM order_entries e
          CROSS JOIN LATERAL (SELECT jsonb_build_object('store_id', e.store_id, 'order_date', e.order_date, 'bottle_count', e.bottle_count,
                    'cash_adjustment', e.cash_adjustment, 'source', e.source, 'review_status', e.review_status,
                    'last_recorded_marker', e.marked_by_user_id) AS j) nv
    """)

    # ------------------------------------------------------------------ triggers on order_entries
    op.execute("""
        CREATE FUNCTION order_entries_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            keep boolean := entry_ctx('keep_creator') = 'on' AND NEW.created_by_user_id IS NOT NULL;
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
            RETURN NEW;
        END
        $$
    """)
    op.execute("CREATE TRIGGER trg_order_entries_stamp BEFORE INSERT ON order_entries FOR EACH ROW EXECUTE FUNCTION order_entries_stamp()")

    op.execute("""
        CREATE FUNCTION order_entries_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            changed boolean;
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
            IF changed THEN
                NEW.version := OLD.version + 1;
                NEW.last_modified_by_user_id := actor;
                NEW.last_modified_by_role := CASE WHEN actor IS NULL THEN NULL ELSE entry_actor_role(actor) END;
                NEW.last_modified_at := clock_timestamp();
            ELSE
                NEW.version := OLD.version;
            END IF;
            IF NEW.review_status IS DISTINCT FROM OLD.review_status THEN
                NEW.reviewed_by_user_id := actor;
                NEW.reviewed_at := clock_timestamp();
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("CREATE TRIGGER trg_order_entries_guard BEFORE UPDATE ON order_entries FOR EACH ROW EXECUTE FUNCTION order_entries_guard()")

    op.execute(f"""
        CREATE FUNCTION order_entries_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            actor uuid := entry_ctx_uuid('actor_id');
            o jsonb := '{{}}'::jsonb;
            n jsonb := '{{}}'::jsonb;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM entry_append_event(NEW.id, NEW.store_id, NEW.organization_id, coalesce(entry_ctx('event_type'), 'CREATED'), NULL,
                                           {TRACKED_JSON_NEW}, NEW.version, actor, entry_ctx('reason'), entry_ctx('comment'));
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                PERFORM entry_append_event(OLD.id, OLD.store_id, OLD.organization_id, 'CLEARED', {TRACKED_JSON_OLD}, NULL, OLD.version,
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
            RETURN NEW;
        END
        $$
    """)
    op.execute("CREATE TRIGGER trg_order_entries_audit AFTER INSERT OR UPDATE OR DELETE ON order_entries FOR EACH ROW EXECUTE FUNCTION order_entries_audit()")


def downgrade() -> None:
    for trg in ("trg_order_entries_audit", "trg_order_entries_guard", "trg_order_entries_stamp"):
        op.execute(f"DROP TRIGGER IF EXISTS {trg} ON order_entries")
    for fn in ("order_entries_audit()", "order_entries_guard()", "order_entries_stamp()", "entry_verify_chain(uuid)",
               "entry_append_event(uuid, uuid, uuid, text, jsonb, jsonb, integer, uuid, text, text)",
               "entry_event_hash(text, uuid, text, uuid, timestamptz, jsonb, jsonb, text, text, integer)",
               "entry_actor_role(uuid)", "entry_ctx_uuid(text)", "entry_ctx(text)"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")
    # The history tables are append-only on purpose: downgrading removes the triggers' protection, then the tables.
    for t in ("order_entry_events", "security_events"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_append_only ON {t}")
        op.execute(f"DROP TRIGGER IF EXISTS trg_append_only_truncate ON {t}")
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("DROP FUNCTION IF EXISTS append_only_guard()")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('entries.team','entries.audit','entries.review'))")
    op.execute("DELETE FROM permissions WHERE code IN ('entries.team','entries.audit','entries.review')")
    op.execute("DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code IN ('team_lead','entry_reviewer'))")
    op.execute("DELETE FROM roles WHERE code IN ('team_lead','entry_reviewer')")
    op.execute("DROP INDEX IF EXISTS ix_users_reports_to")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS reports_to_user_id")
    for ix in ("uq_order_entries_creator_request", "ix_order_entries_review", "ix_order_entries_unverified", "ix_order_entries_creator_date"):
        op.execute(f"DROP INDEX IF EXISTS {ix}")
    op.execute("ALTER TABLE order_entries DROP CONSTRAINT IF EXISTS ck_order_entries_review_status")
    for col in ("source_app", "request_id", "client_submitted_at", "reviewed_at", "reviewed_by_user_id", "review_status", "last_modified_at",
                "last_modified_by_role", "last_modified_by_user_id", "version", "created_via", "creator_verified", "created_by_code",
                "created_by_name", "created_by_role", "created_by_user_id"):
        op.execute(f"ALTER TABLE order_entries DROP COLUMN IF EXISTS {col}")
