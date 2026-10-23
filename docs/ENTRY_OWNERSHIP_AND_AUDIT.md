# Entry ownership, the four levels, and the audit trail

Written for: the developer who maintains the CRM.

## The four levels

The names are generic. The rules live in one place: `backend/app/core/entry_access.py`.

| | Entry Contributor | Team Lead | Entry Reviewer | Administrator |
|---|---|---|---|---|
| Who | role `employee` (everyone by default) | role `team_lead` (permission `entries.team`) | role `entry_reviewer` (`entries.audit` + `entries.review`) | role `admin`, and the developer |
| Create entries | yes, for their stores | yes (recorded as the Team Lead) | only if they also hold the employee role | yes |
| See entries | **only their own** | own + people who report to them | everything in scope (whole company, or one platform if the account has one) | everything |
| Change a submitted entry | **no** | yes, inside the team, with a reason | **no** (flags only) | yes, with a reason (`PATCH /entries/{id}`) or the existing correct-entries page |
| Delete an entry | no | no | no | yes (kept in history and `deleted_rows`) |
| History of an entry | no | yes, inside the team | yes | yes |
| Store Audit, attempts, security log | no | no | yes | yes |
| Review marks (reviewed / flagged / needs correction) | no | no | yes | yes |
| Assign roles / reporting line | no | no | no | yes (never their own) |

* A contributor still sees that a day was marked by someone else (so it cannot be marked twice) but never the number, the name or the time.
  The same goes for the store's monthly totals, the vendors page and "My entries": they count the person's own numbers only.
* Permissions are re-read from the database on every request; the sign-in token carries identity only. A role change therefore applies on
  the person's very next request. There is no cached role anywhere.
* Nobody is promoted automatically. Existing accounts keep exactly the access they had; Team Lead and Reviewer are given by an administrator in
  Users & access > Edit > Entry role, and every change is written to the security log.

## Where ownership and history are enforced: the database

Migration `0052` adds triggers on `order_entries`, so every writer is covered (employee marks, admin corrections, sheet imports, restores, cash tools,
repair tools, hand-typed SQL) and a new code path cannot forget.

1. The API attaches the **authenticated** user to the database session (`app/core/audit_context.py`, called from the auth dependency).
   Nothing the phone sends can set it.
2. `trg_order_entries_stamp` (BEFORE INSERT) writes `created_by_user_id`, the creator's name / code / role **at that time**,
   `creator_verified = true`, `created_via` (android_app, web_crm, order_sheet_import_*, ...) and the server's clock in `created_at`.
   The phone's clock goes to `client_submitted_at` (diagnosis only). A write with **no** known actor is stored with no creator and
   `creator_verified = false`: never guessed.
3. `trg_order_entries_guard` (BEFORE UPDATE) refuses any change to the creator, its snapshot, `created_at`, `request_id`; bumps `version`
   when a value changes; fills `last_modified_by_*` / `last_modified_at`.
4. `trg_order_entries_audit` (AFTER) appends to `order_entry_events` in the **same transaction**: CREATED, EDITED, CLEARED, RESTORED, REVIEWED,
   FLAGGED, NEEDS_CORRECTION, STATUS_CHANGED, with previous and new values of the changed fields, the actor's identity and role at that time, the
   reason / comment, request id, source and version.
5. `order_entry_events` and `security_events` are append-only: UPDATE, DELETE and TRUNCATE raise an error. Each event stores the hash of the previous
   event of the same entry; `entry_verify_chain(entry_id)` recomputes it. This detects a rewrite made with the protection switched off (tested); it is
   not claimed to stop someone who controls the database server, who could rewrite a whole chain.

`marked_by_user_id` is kept for compatibility and now only means "last person who set the number". Visibility uses the creator, or (for a day a
developer's cash adjustment created first) the person who entered the employee's number.

## API

| Endpoint | Who | What |
|---|---|---|
| `GET /entries/search` | Team Lead (team), Reviewer / Admin (scope) | server-side, paginated, combinable filters: store (partial), store id, outlet id, entry id, creator, creator id / role, team lead, last modifier, day range, created-at range (Indian time unless an offset is given), review status, edited, flagged, unverified creator, refused attempt, same-number-again, source, `deleted=true` for removed entries |
| `GET /entries/{id}` | same, inside scope | the entry plus its full timeline, the attempts for that store and day, and `chain_ok` |
| `PATCH /entries/{id}` | Team Lead (team), Admin | `{bottle_count, reason (>= 5 chars), expected_version}`; extra fields are refused (422); a stale version answers 409 with the current version |
| `POST /entries/{id}/review` | Reviewer, Admin | reviewed / flagged / needs_correction / clear; a flag needs a comment; never touches value, creator or version |
| `GET /entries/attempts`, `/entries/security-events` | Reviewer, Admin | every try to mark (saved, refused, same number again); refused / sensitive actions |
| `GET /entries/team`, `/entries/leads` | Team Lead / Admin | people in the team; the Team Leads to choose from |
| `PUT /employees/{id}/entry-role` | Admin | `{level, reports_to_id}` |
| `POST /orders/mark`, `/orders/mark-many` | contributors and up | accept `Idempotency-Key` and `X-Client-Time`; saved days come back with `entry_id`, `version`, `saved_at` |

An entry id outside the caller's scope answers **404**, the same as a made-up id, and the attempt is written to `security_events`.
Unauthenticated requests get 401. Responses of the audit endpoints are `Cache-Control: no-store`; the web client keeps no audit data once a screen is left.

## Retries and "saved"

* The web and Android apps send one `Idempotency-Key` per submission and reuse it on every retry. The server also treats "the same person sends
  the same number for a day they already saved" as a successful retry (older apps send no key): nothing is written twice, and the answer is not
  a confusing "already marked".
* The Android mark screen says **Saved on the server** only from the server's per-day confirmation; **NOT saved yet** (with Retry, same key) when
  the request fails or times out; "saved / not saved" per date otherwise. Marking is online-only by design; there is no offline queue for entries.
* Every attempt, saved or refused, is written to the immutable `order_mark_journal` (this was built but **never called** before) and appears in
  Store Audit > Attempts.
* The offline **bottle-scan** queue was one list for the whole phone. A scan left unsent by one person would have been sent with the next
  person's login. Every queued scan now carries its owner; only the signed-in owner's scans are shown or sent, and a flush stops if the
  account changes (tested in `mobile/src/lib/scanOwnership.test.ts`). Scans queued by older app versions have no owner: they are kept, never sent.

## Existing data

Nothing was deleted or renamed. For each existing entry the migration fills the creator **only** where the activity log proves it: the latest
`order.marked` event for that store and day is by the entry's current marker and the entry is still an employee entry (verified on old-style data in
`tests/test_migration_0052.py`). Every other entry keeps `creator_verified = false`, no creator, and its old marker as "last recorded marker". Each
entry gets a BASELINE event. In Store Audit, filter "Creator not verified" lists them.

## Known limits and decisions

* **Store-level aggregates stay visible by design**: Zepto capping status, printed store cards and their public QR page show store totals, not
  entries. Say if any of these should also be restricted.
* Employees can no longer correct their own saved entry (the earlier "edit my own count" feature). `EMPLOYEE_CAN_CORRECT_OWN=true` brings it back;
  every such change is still audited.
* A Team Lead can only correct entries whose creator is verified. Unverified legacy entries are an administrator's to investigate.
* The activity-log retention job (60 days) deletes old `order.marked` rows. Run migration 0052 **before** the first night purge after deploy, or the
  proof for older entries is lost (they then stay "not verified"). The new history tables are not purged.
* The database trigger copies each deleted `audit_logs` row to `deleted_rows`; the purge removes those copies too (see `audit_retention.py`).
* Android needs a new build for: masked days, Saved / NOT saved confirmation, per-account scan queue and the Forgot password screen.

## Deploy and rollout

1. Deploy the backend (the release command runs `alembic upgrade head`: 0052 adds columns, triggers, roles and the baseline events; measured on a laptop: about 80 s for 300,000 entries;
   one audited edit adds about 70 ms, a 1,500-entry sheet overwrite 0.4 s. Production hardware will differ: time it on a copy first).
2. `GET /api/v1/ready` should show revision `0052`.
3. Sign in as an administrator: open **Store Audit**, search a store you know, open an entry, check the creator and the timeline.
4. Users & access > Edit > Entry role: make one real Team Lead and set who reports to them; make one Entry Reviewer. Check each sees only what they should.
5. Publish the web app, then the Android build. Old app versions keep working (no key needed; the server de-duplicates by creator and number).
6. For a week watch Store Audit > Attempts (refused) and > Security log; ask anyone who reports a wrong entry for the entry id.
7. Rollback: the app code is backward compatible with the new columns; do not downgrade the migration after real entries exist (it drops the history tables).
