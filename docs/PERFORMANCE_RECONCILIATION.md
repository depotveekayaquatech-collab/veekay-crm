# Performance reports: what they measure, and how to explain a change

## What the numbers are (definition `coverage-3`)

The pasted report says `Entries - 2,462 / 4,563`, `Percentage - 54.0%`. Read it as:

| Part | Meaning |
|---|---|
| total | live stores in that employee's scope **x** judged days (a store-day is the unit of work; this is not a count of entry records) |
| "Entries" | how many of those store-days **have an entry today, whoever entered it**: the employee, a colleague, a Team Lead, a spreadsheet upload by the Developer User, older data |
| judged days | **every** day from the 1st up to **yesterday (Asia/Kolkata)**. The holiday calendar is not consulted |
| `Percentage` | entries / total, one decimal, never rounded up to 100 |
| `entries_made` (separate) | entries this person **created** on the platform this month (any store) |
| `corrected` / `correction_events` (separate) | **distinct entries** whose number they changed / **every** change |
| Attendance (separate module) | attendance records, weekly offs and **holidays**; never mixed into the above |

Two rules are fixed on purpose:

* **Holidays are attendance's business.** An entry dated on a holiday counts like any other. Declaring, changing or removing a holiday (today or for a past date) cannot change any
  entry count, total or percentage. (A holiday only changes attendance, leave and payroll, and the zero-streak review treats a *missing* holiday entry as neutral.)
* **Who or what entered an entry never decides whether it counts.** It counts for the employee whose scope holds the store. The creator and the import source stay on the entry
  (`created_by_*`, `created_via`) and are shown in reconciliation for audit only. A live store in **nobody's** scope is credited to nobody and listed in `summary.unassigned_stores`.
  (A `0` in a spreadsheet is not imported by the sheet sync, by existing design: the CRM has no zero entry there.)

The figure is **recounted on every look**, so it changes only when the underlying records do:

1. an entry is **added late** to an earlier day;
2. a **new day finishes** (judged at midnight IST, when most of it is not yet entered, so the percentage dips);
3. an entry is **cleared** or **moved**;
4. a **store changes hands** (state reassigned, store closed or opened, scope edited).

## Explaining a change (admins and entry reviewers)

Orders > Performance > **Why did a number change?** (`/orders/performance/reconcile`), or the API/CLI below. Pick an earlier and a later moment: a kept report, a time
rebuilt from the records, or right now. Every employee's difference is split **exactly** into: newly finished day, entries added, entries removed (who, when, reason,
the entry's full history), stores gained / lost. Anything the records cannot account for is **unexplained** and puts the employee (and the
report) in *Requires review*. Statuses: *Verified*, *Reconciled with legitimate changes*, *Requires review*, *Unable to verify: missing historical evidence*.
A decrease is never labelled misconduct: it is a data difference until the records say why.

```
GET  /orders/performance/reconciliation?partner=blinkit&month=2026-10&previous_at=2026-10-29T10:37:00%2B05:30&current_at=2026-10-30T10:37:00%2B05:30
GET  /orders/performance/snapshots?partner=blinkit&month=2026-10          # kept reports
POST /orders/performance/snapshots                                        # keep the report as it is now ({"partner","month","revision_of","revision_reason"})
GET  /orders/performance/snapshots/{id}?partner=blinkit                    # rebuild it from the records and compare with what it stored
python scripts/performance_reconcile.py --partner blinkit --previous 2026-10-29T10:37+05:30 --current 2026-10-30T10:37+05:30   # read-only
```

Access is decided by the backend from the caller's roles and permissions on every request (`entry_access.scope_for`): administrators, the developer and Entry Reviewers
only; a platform-scoped reviewer only for their platform. No new role or permission was added.

## Kept reports (`performance_snapshots`, migration 0062)

Once a morning (10:30 IST, `PERFORMANCE_SNAPSHOT_*`), and each time an administrator **copies** a report to send it (the exact text is kept), the report of every platform is
stored: per-employee figures, the judged days it used, the store list behind each employee, and the instant of the data (`generated_at`). The table is
**append-only**: the database refuses UPDATE, DELETE and TRUNCATE. A correction is a **new** snapshot with `revision_of` and a mandatory `revision_reason`; the original is
never touched. A snapshot is a record of what was *reported*; **Check against the records** rebuilds it from the data of its instant and says whether it reproduces.
Each is built in one `REPEATABLE READ` transaction, so entries arriving meanwhile are in all of it or none of it.

## What is proven, what is inferred

Rebuilt from records the database protects: `order_entries.created_at` (never changeable), `deleted_rows` (copy + instant of every deletion, since migration 0043 on
19 Oct 2026), `order_entry_events` (who cleared / moved an entry, and why; hash-chained).

Limits, stated so nobody over-trusts a screen:

* **Past store scopes are not recorded.** Assignments, exclusions and store status are overwritten in place. A kept report stores its own store lists; a time rebuilt without
  one assumes *today's* scope and says so. A scope change in between shows as a difference it cannot name.
* Before 19 Oct 2026 a deleted entry left no copy: such moments are *Unable to verify*.
* A deletion is stamped with its transaction's start time; an entry created in a transaction that began earlier than a snapshot but committed after it can differ by that
  gap. `Check against the records` shows any such difference instead of hiding it.
* A clearing with no signed-in actor, or a deleted entry with no clearing event, proves the entry went but not by whom: it is reported as unexplained.
* Reasons for clearing are optional in the app; "no reason recorded" is shown as such.
