# Entry ownership, the four levels, and the audit trail

Written for: the developer who maintains the CRM.

## The four levels

The names are generic. The rules live in one place: `backend/app/core/entry_access.py`.

| | Level 1: Data Entry | Level 2: Team Lead | Level 3: Reviewer | Level 4: Administrator |
|---|---|---|---|---|
| Who | role `employee` (everyone by default) | role `team_lead` (permission `entries.team`) | role `entry_reviewer` (`entries.audit` + `entries.review`) | role `admin`, and the developer |
| Create entries | yes, for their stores | yes (recorded as the Team Lead) | only if they also hold the employee role | yes |
| See entries | **their own, plus numbers set by someone more senior (read-only)** | own + people who report to them, plus numbers set by someone more senior | everything in scope (whole company, or one platform if the account has one) | everything |
| Change a submitted entry | **no** | yes, inside the team, with a reason, **only while it is still Submitted** (the edit also verifies it) | **yes, any entry, with a reason; the edit is final** (`PATCH /entries/{id}`) | yes, with a reason (`PATCH /entries/{id}`) or the existing correct-entries page; the edit is final |
| Verify / review | no | verify a Submitted entry of the team | review any entry directly (the shortcut), or ask the Team Lead to check it | same as Level 3 |
| Cash purchase import + manual add, random card PDF | no (403) | no (403) | yes (the PDF still needs the access code) | yes |
| Delete an entry | no | no | no | yes (kept in history and `deleted_rows`) |
| History of an entry | no | yes, inside the team | yes | yes |
| Store Audit, attempts, security log | no | no | yes | yes |
| Review marks (reviewed / flagged / needs correction) | no | no | yes | yes |
| Assign roles / reporting line | no | no | no | yes (never their own) |

* **Who sees whose number.** Seniority order: contributor < Team Lead < reviewer < administrator / developer. A person sees their own numbers and
  the numbers whose *current value was set by someone strictly more senior* (judged by the role stamped on the entry when it was set): a contributor
  sees what a Team Lead, an administrator or the developer entered, and cannot change it (marked `by_higher` in the calendar). People at the same
  level never see each other's numbers: a day a colleague marked shows as marked, with no number, name or time. A number a more senior person has
  corrected counts as theirs from then on. A day carrying a developer's cash adjustment stays hidden from everyone below the developer.
  Store totals, the vendors page and the Orders list follow the same rule; "My entries" lists only what the person entered themselves.
  An old entry with no known creator is shown if an administrator last set its number, and hidden otherwise.
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
| `POST /entries/{id}/review` | Reviewer, Admin | `reviewed` = finalise directly (Reviewed, the Team Lead is no longer needed); flagged / needs_correction / clear set the review mark; a flag needs a comment; never touches value, creator or version |
| `POST /entries/{id}/verify` | Team Lead (own team) | Submitted -> Verified by Team Lead; 409 if it is no longer Submitted |
| `POST /entries/{id}/request-check` | Reviewer, Admin | ask the creator's Team Lead to check a Submitted entry: an open request on the entry plus an in-app notification |
| `POST /entries/{id}/comments` | Team Lead (team), Reviewer, Admin | a comment appended to the entry's history |
| `GET /entries/options?kind=store\|person&q=` | Team Lead (team), Reviewer, Admin | typeahead for the Store-wise and Employee-wise filters, inside the caller's scope |
| `GET /entries/summary` | Team Lead (team), Reviewer, Admin | entries per state over the last 30 days |
| `GET /entries/attempts`, `/entries/security-events` | Reviewer, Admin | every try to mark (saved, refused, same number again); refused / sensitive actions |
| `GET /entries/team`, `/entries/leads` | Team Lead / Admin | people in the team; the Team Leads to choose from |
| `PUT /employees/{id}/entry-role` | Admin | `{level, reports_to_id}` |
| `POST /orders/mark`, `/orders/mark-many` | contributors and up | accept `Idempotency-Key` and `X-Client-Time`; saved days come back with `entry_id`, `version`, `saved_at` |

An entry id outside the caller's scope answers **404**, the same as a made-up id, and the attempt is written to `security_events`.
Unauthenticated requests get 401. Responses of the audit endpoints are `Cache-Control: no-store`; the web client keeps no audit data once a screen is left.

## The verification workflow (migration 0053)

`Submitted (L1)` -> `Verified by Team Lead (L2)` -> `Reviewed by Reviewer (L3)`, stored in `order_entries.verification_status` and moved by the database
triggers from **who changed the number**, so every writer is covered:

* a new entry starts `submitted`, unless a more senior person created it (a Team Lead's own entry is `verified_l2`; an administrator's or reviewer's is `reviewed_l3`);
* a changed number moves the entry to the state of whoever changed it: Team Lead -> `verified_l2` (only while it was `submitted`; the database refuses a Team Lead
  changing anything already verified or reviewed), Reviewer / administrator -> `reviewed_l3`, the contributor or an unknown writer -> back to `submitted`;
* without a number change the state only moves forward (Team Lead and above may verify a `submitted` entry; Reviewer and above may finalise any). **Reviewer shortcut:**
  finalising a `submitted` entry directly skips Level 2 for good, and writes no `VERIFIED_L2` event;
* a Reviewer can **request a check**: `check_requested_*` is an open request on a `submitted` entry, shown to the Team Lead as "Verification requested" (filter
  `verification=requested`) with an in-app notification (kind `entry_check`) to the creator's Team Lead; the next verification or change clears it. A creator with no
  Team Lead assigned is recorded and the answer says nobody was notified.

**Reports show the final value only.** `bottle_count` is always the number of the current state (the L1 value until a senior changes it, then theirs), and every report
reads it. Earlier values exist only in `order_entry_events`, never in a report or export. History is never overwritten: each step appends `EDITED`, `VERIFIED_L2`,
`REVIEWED_L3`, `CHECK_REQUESTED`, `STATUS_CHANGED` or `COMMENTED` (a comment is appended with `entry_append_event`, on the same hash chain).

**Level 1 sees changes.** `GET /orders/calendar` and `GET /orders/my-entries` carry `changed` (who, in which role, when, old and new number, the reason) and `verification`
(the state). A developer's hidden cash adjustment is never reported and names nobody.

**Existing entries.** All start `submitted` (nobody verified them); a `reviewed` mark from 0052 becomes `reviewed_l3`. The Team Lead's default list is the last pending
entries, so the old backlog does not flood it; to settle the backlog in one go an administrator can run, for example,
`UPDATE order_entries SET verification_status = 'reviewed_l3', l3_reviewed_at = now() WHERE order_date < '2026-10-01' AND verification_status = 'submitted'`
**with an actor set** (`SELECT set_config('app.actor_id', '<a reviewer id>', true)` in the same transaction; the trigger refuses it otherwise). Migration 0053 takes about 2 s
on 300,000 entries (measured on a laptop).

## Verifying a whole store at once

Opening one store (from Entries to Verify or Entry Review) shows the store card, a month calendar coloured by verification state, then the entries audit. `GET /entries/store-review` feeds the calendar; `POST /entries/verify-store` is the single "Verify store" button: a Team Lead verifies every `submitted` entry of the store in view, a Reviewer / administrator reviews every entry not yet reviewed. It covers the chosen employee and day range when set, never leaves the caller's scope, writes one history row per entry (same as the per-entry buttons), skips flagged / needs-correction entries, and refuses more than 3000 entries in one go.

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
* Level 3 and Level 4 now also hold the two tools that were developer-only (`cash.adjust`: cash purchase sheet import and manual add; `cards.sheet`: the random card PDF,
  still behind its access code). They are computed per request in `UserRepository.get_permission_codes`; they stay reserved (never grantable per person), a reviewer limited
  to one platform does not get them, and Level 1 / Level 2 get 403.
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
