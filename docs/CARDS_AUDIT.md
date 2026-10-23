# How the CRM builds vendor / store cards: audit for the WhatsApp plan

Written for: the owner, to decide how to send each vendor their card PDF on WhatsApp on the 2nd (previous month) and the 15th (this month, till date).

Read-only audit. No code was changed, nothing was sent, production was not touched (Fly was only asked for its machine size and the **names** of its secrets; no secret value and no `.env` file was read).
Tags: **VERIFIED** = seen in code or in output I produced. **UNKNOWN** = could not be confirmed from here.
Paths are relative to the repository root; `card_service.py` = `backend/app/services/card_service.py`.

> **About the numbers in sections 3 and 6.** There is no real vendor data on this computer (only a 5-store test seed). Everything measured below was run on a **synthetic**
> scratch database I built to look like production: 1,500 stores (1,100 Blinkit, 400 Zepto), about 190 vendor spellings, deliberately messy vendor names and phone formats,
> about 69,000 order entries for September and October. The counts therefore show **how the code behaves**, not how your real data looks. The same queries are in
> section 3 so they can be run on the real database (read-only) by you or with your go-ahead.

---

## 0. One paragraph: how a card is built, from click to PDF

On **Store cards** (`/cards`, `src/features/cards/CardsPage.tsx`) a user with the `orders.view` permission picks platform, region and (optionally) a month, ticks vendors and
clicks **Download PDF** (one vendor) or **Download ZIP** (several). The browser calls `GET /api/v1/cards/pdf` or `POST /api/v1/cards/zip`
(`backend/app/api/v1/endpoints/cards.py:100,125`). `card_service.build_pdf` / `build_zip` (`card_service.py:696,722`) load the stores the user may print
(admin: the whole organisation; an employee: only their own stores), keep the ones that qualify for the chosen month, group them by the vendor name stored on each store, read that month's
`order_entries` rows (final `bottle_count`, one row per store per day) and draw **one A4 page per store** with ReportLab (`_draw_card`, `card_service.py:561`): month line, company band with
the contact number(s) of the region / state employee, logo, vendor, a signed QR code, store details and two 15- and 16-row tables that list that month's entries in date order with a
TOTAL COUNT. The PDF is generated on request and returned in the response: nothing is cached or stored.

---

## 1. Which card is this, exactly?

### 1.1 Every PDF generator in the repo (VERIFIED by searching for reportlab / pymupdf / qrcode)

| What | File : function | Endpoint | Permission | Used for |
|---|---|---|---|---|
| **Monthwise virtual card** (blank, or filled for a month) | `card_service.py:696 build_pdf`, `:722 build_zip` | `GET /cards/pdf`, `POST /cards/zip` (`cards.py:100,125`) | `orders.view` | The vendor-wise cards printed / downloaded from **Store cards**. **This is the one for vendors.** |
| Public QR page (not a PDF) | `card_service.py:183 public_count` | `GET /public/count` (`cards.py:145`), `GET /count` (`app/main.py:162`) | none (HMAC link) | What the QR on a card opens |
| Cards from an uploaded sheet ("Random Count PDF") | `card_sheet_service.py:463 render`, `:502 render_random`; `card_sheet_bulk.py:180` | `/developer/card-sheet/*` (`card_sheet.py:74,90`) | `cards.sheet` (developer only) + access code | Same card look, filled from a sheet instead of orders. Developer tool. |
| Bottle QR labels | `bottle_service.py:170 labels_pdf`, `:182 render_labels`, `:222 replacement_label_pdf` | `/bottles/batches/{id}/labels.pdf`, `/bottles/{serial}/label.pdf` (`bottles.py:86,115`) | `bottles.manage` | Stickers for bottles, nothing to do with vendors |
| Compliance summary PDF | `compliance_repo_service.py:284 summary_pdf` (PyMuPDF) | `POST /compliance/summary-pdf` (`compliance.py:90`) | compliance permissions | Merges uploaded store documents; not a card |

### 1.2 The vendor-wise PDF a user downloads today
Web page **Store cards** (sidebar item; route `/cards`, `src/app/router.tsx:112`). Per vendor row the **PDF** button, and the bottom button **Download PDF** / **Download ZIP (n PDFs)**
(`CardsPage.tsx`, `download()` and `downloadStore()`): `apiBlob("/cards/pdf?…")` and `apiBlob("/cards/zip", {vendors, partner, region, month})`. Clicking a store chip under a vendor downloads that single store's card.
The Android app has a **Store cards** screen too, but it is the compliance "card photo" upload (`mobile/src/app/staff/cards.tsx`), not this PDF.

### 1.3 Standard card vs monthwise card (VERIFIED)
There is **one template**, not two. With **no month** it is the blank "standard" card: a write-in line "Month of - ______", empty tables. With a **month** it is the monthwise card: "Month of - SEP-2026" and the tables filled
(`_draw_card`, `card_service.py:565-574`, `:652-655`; docstring `:1-21`). Both have the same columns: `#`, `Date`, `Filled Bottle`, `Empty Bottle`, `Signature`; **Empty Bottle and Signature are always blank**
(`_log_table`, `:500-540`). For vendors on WhatsApp the month version is the one that makes sense.

### 1.4 Parameters and defaults (VERIFIED, `cards.py:75-142`, `card_service.py:696-760`)
| Endpoint | Parameters | Defaults / rules |
|---|---|---|
| `GET /cards/vendors` | `partner` (slug), `region` (uuid), `q` (search, min 2 chars), `month` (`YYYY-MM`) | all omitted = all live stores, all vendors, blank-card mode. Returns vendors with store counts, regions, months that have entries. |
| `GET /cards/pdf` | `vendor`, `store_id`, `partner`, `region`, `month` | needs `vendor` or `store_id`, else 422. No `month` = blank cards. `store_id` = that one store, any status, any month. |
| `POST /cards/zip` | `vendors[]` (1-300), `partner`, `region`, `month` | one PDF per vendor inside the ZIP. |
| python `build_pdf(db, user, is_admin, partner, vendor, month, store_id, region)` | same | `month` is a **date** (first of the month) or `None`. |
`is_admin` = the caller holds `orders.correct` (`cards.py:71-72`). Non-admins only get stores assigned to them (`card_service.py:240-266`).

### 1.5 One PDF per vendor, one page per store; limits (VERIFIED)
Yes: `_render` draws one page per store (`card_service.py:677-689`). Limits: **600 stores per PDF** (`MAX_STORES_PER_PDF`, `:49`, enforced `:712-713` with HTTP 422), **1,500 cards per ZIP** (`:50`, `:737-738`),
**300 vendors per ZIP request** (`cards.py:53`). A vendor with 1 store = a 1-page PDF; 50 stores = 50 pages; 600+ stores = refused with "pick fewer". Page count therefore equals store count.

---

## 2. Where the data comes from

### 2.1 Tables and columns read (VERIFIED)
| Table.column | Used for | Where |
|---|---|---|
| `stores.id, name, external_code (Outlet ID), entity, state, city, status, vendor_name, vendor_number, poc_*, partner_organization_id, region_id, organization_id` | card content, grouping, search, filtering | `card_service.py:240-292, 561-662`; model `app/models/store.py:47-65` |
| `organizations.name / slug` (the platform) | "Channel:" line, `partner` filter | `card_service.py:685`, `:259-265` |
| `regions.name` | "Region" cell | `:645` |
| `order_entries.store_id, order_date, bottle_count` | the log table and TOTAL; also "supplied that month" test (`bottle_count > 0`) | `card_service.py:213-237, 665-674` |
| `users.phone, is_active, region_id, platform_organization_id, employee_code` | the contact number printed | `card_service.py:391-415` (`_Contacts`) |
| `state_assignments (assigned_user_id, state, partner_organization_id)` | Zepto: the employee a state is assigned to | `:396-402` |
| Employee scope tables (via `assignment_service.visible_stores`) | non-admin users only get their own stores | `card_service.py:262`, `assignment_service.py:114` |
| `store_vendor_periods` | **not used by cards** (see 3.3) | no import in `card_service.py` |

### 2.2 The query for the daily entries (VERIFIED, `card_service.py:665-674`)
```python
select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count)
  .where(OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= month, OrderEntry.order_date <= end)
  .order_by(OrderEntry.order_date)
```
One query for all stores of the PDF (or of the whole ZIP). Every row of the month is returned, **including a marked 0** (a 0 is a real entry).

### 2.3 The final bottle count (VERIFIED)
The column shown is `order_entries.bottle_count`, which the model defines as "always the **FINAL** number (what every report shows)"; a developer's cash-purchase adjustment is already inside it
(`app/models/order_entry.py:44-46`; `bottle_count - cash_adjustment` is the employee's own part). So **a card shows the final number, including cash adjustments and any admin / developer
correction**, whoever entered it. Edits overwrite the same row, so the card always shows the latest value.

### 2.4 Which stores are included for a month (VERIFIED, `card_service.py:213-266`)
* **A month is chosen**: exactly the stores that have **at least one entry with bottles > 0 in that month**, whatever their status now (live, pending or closed) and whatever their start date says
  (`_supplied_in_month` `:213-218`; `_in_month` `:221-237`; admin path `:240-257`). A store nobody marked that month gets **no** card.
* **No month** (blank cards): **live** stores only (`_in_month` `:230-231`, admin path `:249-250`).
* One explicitly chosen store (`store_id`): any status, any month, even with no bottles (`_stores_any_status`, `:268-292`; `build_pdf` `:701-705`).

### 2.5 Excluded stores (VERIFIED)
With a month: stores with no bottles that month (including all-zero months), and for non-admins stores outside their scope. Closed, pending and test stores are **not** excluded by status when they were supplied that month.
There is **no "test store" flag** in the model (`store.py:36-65` has only `LIVE / PENDING / CLOSE`), so test stores would be included if they have entries.

### 2.6 Dates and time zones (VERIFIED, with a caveat)
* `order_entries.order_date` is a plain calendar date (no time, no zone).
* The card code decides "today" and "which months are allowed" with **UTC**: `_today()` = `datetime.now(timezone.utc).date()` (`card_service.py:63-64`); `parse_card_month` rejects a month later than the current UTC month and earlier than 36 months back
  (`:84-89`, `:110-123`). The same UTC "today" is used by order marking (`order_service.py:58-59 _today`, used by `_check_order_date`).
* **Consequence:** between 00:00 and 05:30 IST (18:30-24:00 UTC) the CRM's "today" is still yesterday. On the 1st/2nd and 15th a job running in that window would think it is the previous day (a job scheduled for 1st-of-month 03:00 IST would still see the old month as "current"). Schedule jobs after 06:00 IST, or the code needs an IST "today". **UNKNOWN impact on real data**, VERIFIED in code.
* Month boundaries: a month is the calendar month of `order_date`; `end` is computed with `calendar.monthrange` (`:666`).

### 2.7 Back-month edit window (VERIFIED)
* Employees may mark **last month** until day **`BACKMONTH_GRACE_DAYS`** (default **7**) of this month (`config.py:208`; `order_service.py:820-836 backmonth_open_until / employee_can_mark_month`). Production does not override it (not among the Fly secret names; not in `fly.toml`). So by default: until the **7th**.
* **Admins and the developer can edit any month, any time** (`_check_order_date(..., allow_any_month=True)`, `order_service.py:839`), and an order-sheet import or the cash tool can change old entries too.
* **So a card for last month sent on the 2nd can still change** (employees until the 7th, admins/imports any time). The latest sensible moment for a "complete" last month is the **8th**; sending on the 2nd is a provisional card.

### 2.8 Current month and a month with no data (VERIFIED, rendered above)
The card for the current month lists the entries that exist so far, in date order; future days have no entries, so their rows stay empty. There is **no "data till DD-MMM" label** on the card: the heading only says `Month of - OCT-2026`. (The QR page says "till date".) A month with no supplied stores returns **404 "No stores found"** (`card_service.py:710-711`), so a vendor with no supply that month simply has no PDF.

### 2.9 Caching / storage (VERIFIED)
Nothing is cached or stored: PDFs are built in memory (`io.BytesIO`, `_render` `:680-689`) and returned with `Cache-Control: private, no-store` (`cards.py:118-122`). The only cache inside is the per-region/state contact lookup for one request (`_Contacts`, `:379-385`). Uploaded files in object storage (Tigris, S3 API) are unrelated to cards.

---

## 3. Vendor identity and grouping

### 3.1 What a "vendor" is (VERIFIED)
A vendor is just **the text in `stores.vendor_name`**. The key is `_vendor_key(s) = (s.vendor_name or "").strip() or "No vendor"` (`card_service.py:295-296`), used at: vendor list grouping `:345`, search matches `:356`, PDF vendor filter `:705, 709`, ZIP grouping `:732-733`. There is no vendor table.

### 3.2 Case, blanks, `NA`, spaces, spellings (VERIFIED)
* **Grouping is case-sensitive and space-sensitive** (`setdefault(_vendor_key(s))`, `:345, :733`): `ABC`, `abc` and `ABC ` (trailing space is stripped, so that one merges) become different vendors when the case differs, and `ABC  Traders` (two spaces) differs from `ABC Traders`.
* **But the PDF filter is case-insensitive** (`:709`, `:732`): choosing `ABC` downloads the cards of `ABC` **and** `abc`. So the list shows two vendors while either click returns both: **inconsistent**.
* **Blank** vendor names become the pseudo-vendor **"No vendor"**.
* **Placeholders are not recognised**: `NA`, `#N/A`, `nan`, `none` become real "vendors" with their own cards. (The vendor-login builder does know a junk list, `external_account_service.py:30`; cards do not use it.)
* Spelling variants (typos, extra words) are separate vendors. Nothing normalises them on sync (`store_sync_service.py:346-350` only strips).

### 3.3 When a store changes vendor (VERIFIED)
The card uses **only the store's current vendor** (`Store.vendor_name`). The vendor-history table `store_vendor_periods` (who supplied a store and for which dates; `app/models/store_vendor_period.py`, kept by `vendor_history_service.py`) is **not read by the card code**. So if store S moved from vendor A to vendor B on the 12th, **the whole of last month's card for S appears under B** (including A's days) and A gets no card for it. This is the main attribution risk for WhatsApp.

### 3.4 Same-name vendors (VERIFIED)
Not distinguished on cards (same exact name = one vendor). The vendor **login** builder does the opposite: it splits one name with different phone numbers into separate people (`external_account_service.py:114-124`). So cards and vendor accounts can disagree about who "the vendor" is.

### 3.5 Read-only vendor report (counts only)
Run on the **synthetic** database (to prove the queries and the code path; the real numbers are **UNKNOWN**):

| Measure | Value (synthetic data, so it reflects the mess I injected, not your real data) |
|---|---|
| Stores | 1,500 (1,100 Blinkit, 400 Zepto), of which 60 are closed |
| Vendor keys as the card code builds them | **190** |
| Vendor keys after ignoring case and extra spaces | **153** (**69** keys are case/space variants of another; **32** vendor names exist in more than one spelling among live stores) |
| Stores per vendor key (min / median / max) | **1 / 6 / 94** |
| Stores with no vendor (blank or null) | **24** (become the pseudo-vendor "No vendor") |
| Stores whose vendor name is a placeholder (NA, #N/A ...) | **19** (each placeholder becomes its own "vendor") |
| Vendor number field: usable 10-digit mobile | **1,306** |
| ... empty | **72** |
| ... several numbers in one field | **76** |
| ... junk / unusable | **46** |
Raw shapes of the vendor number field, digits shown as 9 (the synthetic file has no real numbers; on real data the same query is in the list below):
`9999999999` x 1215, `+99 99999 99999` x 91, `9999999999 / 9999999999` x 76, `<empty>` x 72, `NA` x 13, `#N/A` x 11, `nill` x 9, `9` x 8, `9999` x 5.

**Queries to run on the real database (read-only; nothing is changed):**
```sql
-- vendors as the card code sees them, and after ignoring case / extra spaces
WITH k AS (SELECT COALESCE(NULLIF(btrim(vendor_name), ''), 'No vendor') AS v FROM stores)
SELECT count(DISTINCT v) AS vendor_keys,
       count(DISTINCT lower(regexp_replace(v, '\s+', ' ', 'g'))) AS keys_ignoring_case_and_spaces FROM k;
-- stores per vendor: min / median / max
SELECT min(c), percentile_cont(0.5) WITHIN GROUP (ORDER BY c) AS median, max(c)
FROM (SELECT count(*) c FROM stores GROUP BY COALESCE(NULLIF(btrim(vendor_name), ''), 'No vendor')) q;
-- stores with no vendor / placeholder vendors
SELECT count(*) FILTER (WHERE btrim(coalesce(vendor_name, '')) = '') AS no_vendor,
       count(*) FILTER (WHERE lower(btrim(vendor_name)) IN ('na','n/a','#n/a','nan','none','nil','null','tbd','unknown','no','nill','-')) AS placeholder
FROM stores;
-- names that are variants of each other (same text ignoring case / spaces, written differently)
SELECT lower(regexp_replace(btrim(vendor_name), '\s+', ' ', 'g')) AS norm, count(DISTINCT btrim(vendor_name)) AS spellings, count(*) AS stores
FROM stores WHERE btrim(coalesce(vendor_name, '')) <> '' GROUP BY 1 HAVING count(DISTINCT btrim(vendor_name)) > 1 ORDER BY 3 DESC LIMIT 50;
-- shapes of the vendor number field (digits shown as 9), most common first
SELECT regexp_replace(coalesce(vendor_number, '<empty>'), '[0-9]', '9', 'g') AS shape, count(*) FROM stores GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
-- usable 10-digit mobile in the field (same idea as external_account_service.primary_number)
SELECT count(*) FILTER (WHERE regexp_replace(coalesce(vendor_number,''), '[\s\-().]', '', 'g') ~ '(^|[^0-9])(\+?91)?[6-9][0-9]{9}($|[^0-9])') AS has_mobile,
       count(*) FILTER (WHERE coalesce(btrim(vendor_number), '') = '') AS empty
FROM stores;
```

### 3.6 Vendor phone numbers: where they live (VERIFIED)
* `stores.vendor_number` (String(32), one free-text field **per store**, `store.py:65`); it can hold several numbers or junk (the sheet sync only strips it).
* `external_accounts.phone` (String(64)) for the **vendor portal accounts**, built by `external_account_service.py` from those store fields. Its `primary_number()` (`:38-42`) extracts the **first 10-digit mobile** from text like `9035454807 / 9108505863` or `+91 90354 54807`. An account is linked to its stores through `external_account_stores`.
* `store_vendor_periods.vendor_number` keeps the number per vendor period.
* **Best source for WhatsApp:** the vendor accounts (`external_accounts` + `external_account_stores`): map each card vendor's stores to an account and use its cleaned `phone`. Where one card vendor's stores belong to **different accounts** (same name, different numbers) the number is ambiguous: needs a human decision.
* The vendor-login generator already produces a CSV `login,password,name,phone` per vendor / POC (`docs/MOBILE_LAUNCH.md:41`), which is a ready-made vendor-phone list once accounts exist.
* Masked examples of the raw shapes from the synthetic data are in 3.5. **Real examples: UNKNOWN** (no real data here).

### 3.7 Consent / opt-in (VERIFIED: none)
No consent or opt-in field exists on stores, vendor periods, external accounts or users (searched `consent`, `opt_in`, `opt-in`, `whatsapp` across `backend/app`, `src`, `mobile/src`: no matches besides an unrelated UI comment). There is also **no WhatsApp code** (section 8). Before sending business-initiated messages Meta requires the recipient's opt-in; this needs a new field or a record kept elsewhere.

---

## 4. What the card looks like (VERIFIED, `card_service.py:422-662`, rendered samples below)

* **Page:** A4 portrait, 595.27 x 841.89 pt; the card is 540 pt wide (`720 px x 0.75`), centred, 8 mm top margin (`:422-426`). One card per page.
* **Fonts:** Helvetica / Helvetica-Bold (ReportLab built-ins; no embedded font). **Colours:** blue theme `#0B6FB8` (main), `#084B7C` (dark), `#E8F2FA` (light band), grey grid (`:53-60`).
* **Logo:** `backend/app/assets/watr-logo.png` (bundled), or the file at `CARD_LOGO_PATH` if set (`:447-455`); if no file works it draws the text "WaTR / VEE KAY AQUATECH" (`:472-480`).
* **Fields in order (top to bottom):**
  1. `Month of  -  SEP-2026` (or a blank write-in line with no month): `month_label(month)` `:67-69, :565-574`.
  2. Company band: `settings.COMPANY_NAME` (default "VEE KAY AQUATECH PVT. LTD."), `Email: COMPANY_EMAIL`, `Contact: <phone(s)>` (`:579-590`).
  3. Logo | "BOTTLE DELIVERY CARD" / `Channel:` platform name in capitals (Blinkit / Zepto) / `Vendor:` (`stores.vendor_name`, one line, ellipsis if too long) | QR code with "Scan to check bottle count till date" (`:592-619`).
  4. Store cells: **Store name**, **Store / Outlet ID** (`external_code`, large), **Entity**, **Region**, **State**, **City**; each cell wraps to 2 lines then "…"; a missing value prints "—" (`:625-648`). **The store address is not printed.**
  5. Two log tables side by side: rows 1-15 on the left, 16-31 on the right (`:654-655`); columns `#`, `Date` (`2-Sep-2026`), `Filled Bottle`, `Empty Bottle` (blank), `Signature` (blank). The right table ends with **TOTAL COUNT** (`:542-556`).
  6. A blue outer border. There is **no remarks or signature block** besides the empty Signature column, and no footer.
* **How the log table is laid out:** entries are written **in date order, one per row, starting at row 1** (`entries[first_no - 1 + r]`, `:525`). The `#` column is a **row counter, not the day of the month**. A day with no entry is not shown as a blank row: the following dates move up (visible in the sample: 25-Sep missing, row 25 shows 26-Sep). Totals are the sum of the listed entries (`:652`). Up to 31 rows (a month has at most 31 entries), so "more than 31 days" cannot occur.
* **QR code:** encodes `PUBLIC_APP_URL + /count?s=<store id>&sig=<signature>` (`qr_url`, `:170-172`). The signature is the first 32 hex characters of HMAC-SHA256 of `count:<store id>` using a key derived from the secret (`sign_store`, `:154-155`; key derivation `:130-150`). It has **no expiry** and works as long as the secret is unchanged. Verification accepts the primary secret, rotated ones and a fallback (`:158-167`). Secret names: **`QR_SIGNING_SECRET`** (comma list allowed for rotation) and, as fallback, **`JWT_SECRET_KEY`**. **In production `QR_SIGNING_SECRET` is not among the secret names, so QR links are signed with the JWT secret: rotating the JWT secret would break every printed QR code.**
* **What the public page shows** (`public_count`, `:183-205`): store name, outlet code, vendor name, platform, bottles this month (till date) and last month (only once last month is on/after `CARDS_FIRST_MONTH`, default `2026-09`), and the time. No login. Wrong signature = a generic 404.
* **Contact numbers printed** (`_Contacts`, `:379-415`): **Blinkit** = phones of the active employees of the **store's region**, ordered by employee code, **max 2**, joined with " / "; **Zepto** = the first active employee the **store's state** is assigned to. Numbers only, no names. Stores without a region (Blinkit) print no contact. These are **your employees' numbers, not the vendor's**.
* **Long names / missing data:** `_wrap` limits text to a width and 1-2 lines then adds "…" (`:429-444`); missing logo falls back to text; missing values print "—".
* **Period heading:** `month_label(month)` -> `SEP-2026` (`:67-69`), drawn at `:573`. The PDF metadata title also carries it (`:682`).

**Short description of page 1 of the September sample (in case the PDF cannot be opened):** at the top "Month of - SEP-2026"; a light-blue band with "VEE KAY AQUATECH PVT. LTD." and "Email: … | Contact: 90******00"; below it the WaTR logo on the left, "BOTTLE DELIVERY CARD / Channel: BLINKIT / Vendor: Demo Vendor 097" in the middle and a QR code on the right; then a 3x2 grid of store name, outlet ID (large, blue), entity, region, state, city; then two tables (rows 1-15 left, 16-31 right) with the dates and filled-bottle counts filled in order and the Empty / Signature columns blank; the last row on the right says TOTAL COUNT with the sum (499 in the sample). Images: `docs/cards-audit/page1_last_month.png`, `page1_current_month.png`.

---

## 5. Period handling for the two sends

### 5.1 `month` end to end (VERIFIED)
Web: `<select>` value `YYYY-MM` -> query string / ZIP body -> `parse_card_month(value)` (`card_service.py:110-123`) -> a `date` (the 1st) or `None` -> `_stores(..., month)` (`:240`) and `_in_month` (`:221`) for which stores -> `_entries_for` (`:665`) for the rows -> `_draw_card(... month ...)` (`:561`) for the heading.

### 5.2 Explicit month, independent of today? (VERIFIED)
**Yes.** `build_pdf` / `build_zip` take `month` as an argument and use it directly. Today's date is used only to **validate** it (not in the future, not older than 36 months, UTC; `:84-89, 110-123`) and for the QR page's "this month / last month". An automatic job can call `build_pdf(db, actor, is_admin=True, partner=None, vendor=<vendor>, month=date(2026, 9, 1))`. It needs a **User** only for `organization_id` (and `is_admin=True` skips the per-user scope), so a job needs a system actor like `scheduler._system_actor` (`core/scheduler.py`). Nothing needs to change in the generator for the month itself.

### 5.3 The 15th (current month, till date)
The card as generated today shows the entries that exist (up to the last day anyone marked), future rows empty. A **"Data till DD-MMM"** label is **not** printed and would be a small code change (one extra line near `:573` using the latest `order_date` of the store's entries, or the generation date). Without it a vendor cannot tell "no delivery" from "not entered yet".

### 5.4 The 2nd (previous month)
Last month is **not final on the 2nd**: employees may still mark it until the **7th** (2.7) and admins / imports at any time. A card sent on the 2nd can differ from one printed on the 8th. Latest sensible time for a final card: the **8th**. If the 2nd is required, label it "provisional" or accept re-sends.

### 5.5 Sheet sync (10:00 IST) before a job; how to check it
* The daily job is `run_daily_store_sync` at **10:00 IST** (`core/scheduler.py:94-125`, `STORE_SYNC_HOUR/MINUTE/TIMEZONE`, `config.py:228-230`); it is protected by a Postgres advisory lock so only one machine/worker runs it.
* **It only pulls sheets if sheet sources are configured** (`execute_sync`, `scheduler.py:40-52`: `if pull_sheets and settings.sheet_sources()` and `settings.order_sheet_sources()`). **The Fly secret names contain no `STORE_SYNC_SHEETS` / `ORDER_SYNC_SHEETS`, and `fly.toml` has none, so the Google Sheet sync appears NOT to be configured in production (VERIFIED for names; UNKNOWN if configured another way).** Orders then come from employee marks, admin corrections and manual sheet uploads (`/orders/import`).
* A run writes one row to the activity log, `action = 'sheet_sync.run'` with counts (`scheduler.py:61-65`); a **failed** run writes nothing (the exception is only logged, `scheduler.py:123-124`). A job can check "a `sheet_sync.run` row exists today after 10:00 IST" (the same check the code uses, `sync.py:48-49, 77`) and treat absence as "not synced". Note the activity-log retention (60 days) keeps these rows long enough.
* An external trigger endpoint already exists for an outside scheduler (`POST /sync/trigger`, `sync.py:67-92`: key-protected via the `X-Sync-Key` header, takes the same lock, ignores a second call within 30 minutes): the same pattern fits a "send cards" job.

---

## 6. Real output

All figures: synthetic database (1,500 stores, 188 vendor spellings, 68,944 entries), local PostgreSQL, one laptop process, ReportLab 4. Memory is the Python process's resident memory read from Windows; the process was at 91 MB after warm-up.

| Run | Cards / pages | PDF size | Time | Memory growth (peak process) |
|---|---|---|---|---|
| Small vendor (5 stores), **last month** (Sept) | 5 / 5 | 93 KB | 0.25 s (first call 0.41 s) | +8 MB (98 MB) |
| Small vendor, **current month** (Oct, till 22 Oct) | 5 / 5 | 92 KB | 0.22 s | +3 MB (98 MB) |
| Same vendor, blank cards (no month) | 5 / 5 | 90 KB | not timed | - |
| Biggest vendor (90 stores), last month | 90 / 90 | 1,106 KB | 2.96 s | +4 MB (99 MB) |
| Biggest vendor (90 stores), current month | 90 / 90 | 1,098 KB | 3.36 s | +7 MB (103 MB) |
| **All vendors, one `build_pdf` call each, last month** | 1,779 / 1,779 over 188 PDFs | 28.1 MB in total | **508 s** (8.5 min) | not captured in that run |
| All vendors, one call each, current month | 1,779 / 1,779 over 188 PDFs | 27.9 MB | **319 s** (5.3 min) | not captured |
| **One `build_zip` of every vendor, last month** | 1,418 cards, 188 PDFs | ZIP 17.6 MB | **51.6 s** | **+37 MB (peak 133 MB)** |
| One `build_zip` of every vendor, current month | 1,418 cards, 188 PDFs | ZIP 17.5 MB | 50.5 s | +25 MB (peak 147 MB) |

What the run showed (VERIFIED by the output above):
* **No failures** in 188 vendors x 2 months. (In the synthetic data every vendor has live, supplied stores. In production a vendor with **no store supplied that month raises HTTP 404 "No stores found"**: a send job must treat that as "nothing to send", not as an error.)
* **Largest PDF: 1.1 MB** (90 pages). Every PDF is far below WhatsApp's 100 MB document limit. About 12 KB per page.
* **Per-vendor calls are slow in a loop** (average 2.7 s per vendor over 188, against 0.25 s for a lone call). Each call reloads every store of the organisation (`_stores`, `card_service.py:240-257`) and re-runs an `IN (all 1,400 ids)` query (`_in_month`, `:230-236`); the query seen running was exactly that. Why it gets slower after the first few calls is **UNVERIFIED**; my hypothesis is PostgreSQL switching to a generic prepared plan after five identical statements. `build_zip` loads everything once and is **10x faster (51 s for all vendors)**: use it, or a loader that reads once, for a bulk job.
* **The two code paths disagree about vendor spelling** (3.2): the per-vendor path produced **1,779 cards** where the ZIP produced **1,418**: **361 duplicate cards (20%)**, because a vendor spelled `Demo Vendor 000` and `demo vendor 000` is two list entries but each PDF filter matches both spellings. In a WhatsApp job the same stores would be sent to the same person twice.
* Memory is small: **under 150 MB for the whole organisation's cards**, so the 1 GB machine is not at risk from one run; the risk is CPU time competing with web requests (about 50 s of one core for a full run).
* Production volume itself is **UNKNOWN**: these numbers scale roughly linearly with the number of stores and pages (about 12 KB and 0.03 s per card in the ZIP path).

Sample files (synthetic data, no real names or numbers), in `docs/cards-audit/`:
`sample_2026-09_3-store-vendor.pdf` (last month), `sample_2026-10_3-store-vendor.pdf` (current month, till date), `sample_blank.pdf` (no month), `page1_last_month.png`, `page1_current_month.png`.

---

## 7. How it runs in production

* **Scheduler (VERIFIED):** `backend/app/core/scheduler.py`, APScheduler `BackgroundScheduler` **inside each web worker**, started from the `app/main.py` lifespan (`:59`, stopped `:63`). Jobs: `daily_store_sync` (cron 10:00 `Asia/Kolkata`, misfire grace 1 h, coalesce; `scheduler.py:152-159`) and `audit_purge` (cron 03:30 IST; `:160-166`). With two workers both schedule the sync; **a Postgres session advisory lock (`pg_try_advisory_lock`, `scheduler.py:71-72, 104`) lets one run**. The purge is not locked but is idempotent.
* **Fly (VERIFIED from `backend/fly.toml` and `fly scale show`):** app `veekay-crm-api`, region `sin`, **1 machine**, `shared-cpu-2x`, **1024 MB**, `WEB_CONCURRENCY=2`, `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5` per worker (max 20 connections), `auto_stop_machines = "off"`, health check `/api/v1/health` every 15 s. Release command: `alembic upgrade head && python scripts/seed.py`.
* **Database connection, pooled or direct: UNKNOWN.** The URL is a secret I did not read. Hint only: the deploy guide's template shows port 5432 (`DEPLOY_FLY_VERCEL.md:26`), which is usually the direct port.
* **File storage (VERIFIED):** S3-compatible bucket (Tigris) via boto3 (`app/core/storage.py`), **private**, served by **pre-signed links** whose lifetime is `S3_URL_EXPIRE_SECONDS` (default 300 s, allowed 30-3600; `config.py:156`; **the secret exists in production, its value is UNKNOWN**). Cards are not stored there.
* **Migrations / Alembic head (VERIFIED):** applied by the release command on every deploy. Current head in the repo and live: **`0052`** (`/api/v1/ready` reported revision 0052 after the last deploy).
* **Tests (VERIFIED):** `backend/tests/test_cards.py` has 26 tests (parametrized cases included) covering months, QR signing, public page, PDF/ZIP (blank, monthly, validation, scope, closed stores). They run against a real PostgreSQL test database (`tests/conftest.py`).
* **Outbound HTTP (VERIFIED):** the app has no HTTP client library: Google sheets use `urllib.request` with timeouts 20 s (token), 60 s (sheet), 30 s (store sync) (`google_sheets.py:66-82`, `store_sync_service.py:129-131`); storage uses boto3; email (when configured) uses `smtplib` with a 15 s timeout (`core/mailer.py`). A WhatsApp sender would need `urllib`/a new library with its own timeouts and retries.

---

## 8. WhatsApp: what exists today

* **Code in the CRM: none (VERIFIED).** Searched the repository (Python, TypeScript, Markdown, JSON, YAML, TOML, Apps Script file types) for `whatsapp`, `graph.facebook`, `waba`, `wa.me`, `UrlFetchApp`, `cloud api`: **no hits** in application code, docs or config (only unrelated library files inside the virtualenv). No tables, no webhook route, no environment variable names. The one mention in the repo is a manual instruction in `docs/MOBILE_LAUNCH.md:41` to send each vendor / POC their login line (from the generated CSV `login,password,name,phone`) by WhatsApp or SMS by hand. No `.gs` / Apps Script file is in this repository.
* **Webhook conflict: UNKNOWN, and important.** A WhatsApp Business app can have **one** webhook callback URL. I cannot see your Apps Script ticket system, so I cannot tell whether it is the current webhook receiver. If it is, the CRM cannot also be registered; the options are: the Apps Script forwards the events it receives to a CRM endpoint, or the CRM becomes the single receiver and forwards to Apps Script. **I need you to confirm whether the Apps Script web app URL is set as the callback URL in Meta's app dashboard.** (Sending messages does not need the webhook; receiving delivery receipts and replies does.)
* **Apps Script sender: not available to me.** Please paste the function (token redacted) and I will report API version, template names, variables, phone formatting and error handling.
* **Approved templates / document header: UNKNOWN** (needs your WhatsApp Manager). A PDF sent outside the 24-hour window must use an approved **template that has a DOCUMENT header**; plain document messages only work inside a 24-hour customer-service window.

---

## 9. What would block automated sending (ranked)

1. **Vendor attribution when a store changes vendor** (3.3): the whole month goes to the current vendor. Needs the card to use `store_vendor_periods` for the month, or a rule to hold such stores for review.
2. **No opt-in record** (3.7) and **no WhatsApp number per vendor** that the cards know: phones are free text per store; the usable source is the vendor accounts (3.6) and some vendors have several numbers or none.
3. **Vendor identity is a text field**: case/space variants, placeholders (`NA`, `#N/A`) and blanks become vendors (3.2). Sending to a pseudo-vendor "NA" must be prevented; case variants would send two PDFs to the same person or split one vendor.
4. **Last month is not final on the 2nd** (5.4): employees can edit until the 7th, admins any time.
5. **UTC "today"** (2.6): a job in the first hours IST of the 1st/2nd or 15th sees the old date. Schedule after 06:00 IST or add an IST today.
6. **Sheet sync probably not configured in production** (5.5): "wait for the 10:00 sync" cannot be the readiness check; use employee marking completeness (per-store pending days) or a manual "data complete" confirmation.
7. **The card layout lists entries by order, not by day** (section 4): a vendor can mistake the `#` column for the day, and missing days are invisible. Consider printing the day number / weekday instead of `#`, and marking missing days.
8. **Cards show the final figure including a developer's cash adjustment** (2.3): confirm vendors are meant to see that.
9. **Large vendors:** one PDF can have up to 600 pages (the code limit) and the per-vendor build re-reads all stores (section 6). WhatsApp documents may be up to 100 MB, so size is fine, but a generation job should use the ZIP path (one load) or be rewritten to load once.
10. **QR signed with the JWT secret** (section 4): rotating `JWT_SECRET_KEY` invalidates printed QR codes. Set `QR_SIGNING_SECRET` to the current value of the JWT secret first (the code supports a comma list for rotation).
11. **Only one machine with 1 GB** runs web + scheduler + PDF work (section 7): a bulk send job must not run inside the web workers at peak time.
12. **Meta rules:** the webhook question (8), templates with a document header, and the 24-hour window.

## 10. What I could not answer, and what I need from you

| Item | Needed |
|---|---|
| Real vendor counts, stores per vendor, duplicate/variant names, phone formats (sections 3.5, 3.6) | Your go-ahead to run the read-only queries against production, or run them yourself and send me the output (they only count; masked) |
| Real PDF timing and size at production data volume (section 6) | Same: either production read access or a recent copy of the database |
| Pooled or direct database connection | Say which, or tell me the host name pattern (not the password) |
| Value of `S3_URL_EXPIRE_SECONDS` in production | Check in Fly (`fly secrets` only shows names), or tell me |
| Apps Script sender, whether it owns the webhook, approved templates | Paste the function (token redacted) and the template list from WhatsApp Manager |
| Whether the Google sheet sync is really off in production | Confirm, or tell me which sheet URLs are used |
| Do vendors consent to WhatsApp? | Where is the opt-in kept today (a sheet, a form)? |
