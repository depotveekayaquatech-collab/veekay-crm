# Blinkit and Zepto as two separate partitions

Status: design for approval (2026-10-22). Nothing in sections 3-7 is built yet; section 2 lists what already exists.

## 1. What the code does today (checked, not assumed)

| Area | Today | Problem |
|---|---|---|
| Stores | one `stores` table; `partner_organization_id` says Blinkit or Zepto. Outlet ID is not unique (migration 0047). A store name is unique per platform by an application rule only. | nothing in the database stops two stores of one platform sharing a name, or a store pointing at a region of the other platform |
| Regions | `regions` belongs to the Veekay organisation, **shared by both platforms** ("partners don't own regions"). Blinkit employees and stores use them; Zepto is scoped by state. | a region such as "North" is one row whose totals mix both platforms |
| Orders, caps, documents, tickets, cash, bottles | linked by `store_id`; the platform is only known through the store | a wrong platform on a store silently moves all of its history and capping |
| Dashboard `/orders/insights` | trend, today's bottles, entries, leaderboard, stores by region and by state are computed **organisation-wide**. Only the platform status counts and the filter list are per platform. | Blinkit and Zepto numbers are added together in most panels |
| Same-named stores on two platforms | per-platform queries are fine. Several importers search **every store of the organisation** by Outlet ID or name: cash-purchase sync (no platform filter at all), the card sheet, the compliance index, the ticket webhook, bottle scans by code. | a Zepto row can land on a Blinkit store that has the same ID or name; this is the likely route for Zepto capping or entries showing up on Blinkit stores |
| Vendor / POC logins | one `external_accounts` table, one email namespace, a `platforms` list | a person who works for both platforms has one login that sees both |

## 2. Already built (this week)

- Outlet name is the store's identity; unique per platform in the importers and in the add / edit forms; never changed after creation.
- Importers (stores, orders, capping, card sheet, cash sync, vendor rates) look at the name first, per platform where they already were.
- Stores > Duplicates, upload issues, per-store **Move to the other platform** (keeps history, drops a Zepto capping number when leaving Zepto), and a **platform check** listing stores that look misfiled.

## 3. Target model: each platform is a partition

One rule: **every row that belongs to a platform carries its platform id, every uniqueness rule includes it, and no query or import can run without naming the platform.**

### 3.1 Data
| Table | Change |
|---|---|
| `regions` | add `partner_organization_id` (NOT NULL). Unique `(partner, code)` and `(partner, lower(name))`. Existing shared regions are copied once per platform that uses them, and stores / employees are re-pointed to their platform's copy. |
| `stores` | unique index on `(partner_organization_id, lower(collapsed name))`, added after the 38 Zepto pairs are merged. Composite foreign key `(partner_organization_id, region_id)` -> `regions(partner_organization_id, id)`: a store can only sit in a region of its own platform. |
| `users` / `employee_regions` | an employee's region must belong to the employee's platform (same composite key). |
| `order_entries`, `store_caps`, `compliance_documents`, `tickets`, `cash_purchases`, `bottles`, `bottle_scans` | add a denormalised `partner_organization_id` with a composite foreign key `(store_id, partner_organization_id)` -> `stores(id, partner_organization_id)`. The database then refuses a row whose platform differs from its store's, and per-platform totals need no join. Done table by table, orders and caps first. |
| `external_accounts` | one account per (person, platform); the login email stays unique per platform. A person on both platforms gets two logins, each seeing one platform. |

### 3.2 Code
- A required `PartnerScope` (platform id + slug) is passed into every importer, sync, report and lookup. Org-wide store indexes in cash sync, card sheet, compliance index, ticket webhook and bottle scans are replaced by per-platform indexes; the platform comes from the sheet source, a platform column, or the logged-in employee.
- Repositories expose `for_partner(scope)`; there is no "all stores of the organisation" helper left except the admin overview, which loops over platforms.
- A test suite builds the same store name and Outlet ID on both platforms and runs every importer, report and API, asserting that nothing crosses.

### 3.3 Dashboard
`GET /orders/insights?partner=<slug>` returns one platform's trend, bottles today / yesterday, entries, leaderboard, stores by **that platform's** regions (Blinkit) or by state (Zepto), attention list, dormant list and status counts. The page shows a **Blinkit | Zepto** switch (both side by side on wide screens) and an optional, clearly labelled **Combined** total. Nothing is added together silently.

### 3.4 Security
- Platform partner logins (Blinkit / Zepto accounts) and vendor / POC logins are limited to their platform in every query, as today; the composite keys add a second, database-level guarantee.
- Phase 4 (optional): PostgreSQL row-level security on `stores`, `order_entries` and the other platform tables, with the platform set per request, so even a forgotten filter returns nothing across platforms.
- Backups and the "deleted rows" archive already record the store id; they gain the platform id with the same migration.

## 4. Order of work (each step is deployable and reversible)
1. **Clean the data** (tools exist): re-upload both sheets, merge the Zepto duplicate pairs, run the platform check and move misfiled stores. *No schema change.*
2. **Dashboard split** and per-platform report totals (no schema change; safe to ship alone).
3. **Platform scope in all importers and lookups** + the collision test suite. *Fixes the likely cause of cross-platform entries and capping.*
4. **Schema, part 1:** `regions.partner_organization_id`, per-platform copies, composite keys on `stores` / employees; unique store name per platform.
5. **Schema, part 2:** denormalised platform id and composite keys on orders, caps, documents, tickets, cash, bottles.
6. **Row-level security** (optional hardening).

Steps 4 and 5 are migrations on production data: each runs first on a copy of the database, with a row-count and total-bottle reconciliation per platform before and after.

## 5. Decisions needed
1. Is a region owned by one platform (Blinkit regions are separate from any Zepto grouping)? Zepto stays state-based with no regions unless you want regions there too.
2. Dashboard default: Blinkit | Zepto switch with a Combined tab, or two stacked sections?
3. Should a vendor / POC who works for both platforms get two logins (recommended) or one login that sees both?
4. Go ahead with step 1 now (data clean-up with the tools already built), then steps 2 and 3?
