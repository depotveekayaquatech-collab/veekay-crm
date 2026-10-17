# Storage audit and policy: files, uploads, retention and cost

Audited and implemented 2026-10-17. Three kinds of statement are kept apart throughout: **repository facts** (read in code or proven by a test), **provider facts** (Tigris's published pricing, read 2026-10-17) and **planning assumptions** (your volumes; nothing here is measured production usage). What could not be verified from the repository is in section 11.

## 0. Read this first: three places where the requested policy meets how employees work today

1. **A literal 1 MB limit on the raw upload would stop every phone photo upload.** The Android app (build 9 and earlier) sends the camera photo as it is (picker quality 0.8, no resizing, `mobile/src/lib/files.ts`): 2-4 MB each. The web app allowed 10-12 MB files. So the 1 MB rule is applied to what is **stored**: the server shrinks every photo to fit 1 MB (and aims for about 300 KB) or refuses it with a clear message. The raw-upload ceiling is a separate setting (`COMPLIANCE_MAX_FILE_MB`, 12). When every client shrinks photos itself, set it to 1 and the literal rule is in force; nothing else changes.
2. **PDFs are now capped at 2 MB (was 12 MB).** A PDF cannot be shrunk without damaging it, so it is a hard limit with a message that suggests photographing the pages. I could not verify what size your real bills and **lab test reports** are: the 7 PDFs on this PC are all under 800 KB (supports your 500 KB average) but none is a test report, and the web test-report screen used to allow 8 MB. If real reports exceed 2 MB, raise `PDF_MAX_FILE_MB` (`fly secrets set PDF_MAX_FILE_MB=5`) rather than editing code. One setting covers store PDFs and other PDFs because your table gives them the same limit.
3. **"Multiple optional attachments per store" already exists, so no new table was created.** The compliance model stores a card, a bill and a payment proof **per store per month**, each with a version history (`compliance_documents` + `compliance_document_versions`). Nothing is mandatory: a store with nothing uploaded is listed with empty slots (tested). Several photos for one slot are merged into one PDF. If you want free-form extra photos per store beyond those three slots (for example three signage photos in the same month), that needs a new attachment table and a migration; I did not build it without your decision.

## 1. How files are stored today (confirmed)

- **Production uses Tigris through the S3 API.** `fly.toml` sets `STORAGE_BACKEND = "s3"`; Fly holds the S3 secrets (names verified, values never read); `/api/v1/ready` reports `storage: {ok: true, backend: "s3"}` (a `HeadBucket` request).
- **One storage module**, [backend/app/core/storage.py](../backend/app/core/storage.py): `save_verified / read / exists / stat / signed_url / list_objects / delete`, backends `local` and `s3`. Keys are validated against `..`, absolute paths and empty parts. Every file in the app goes through it. Nothing in the application calls `delete` (a test enforces that).
- **Neon holds only the key and metadata** (name, content type, size, sha256, backend). Never bytes, never a link. Signed links are generated per request and are not saved.
- **Uploads go through the API (Fly) to the bucket**, then back out through a signed link or the API. Fly's disk is not used for files.

## 2. Every file workflow

| Workflow | Upload → function | Stored key (always unique) | Neon record | Opened how | Access check |
|---|---|---|---|---|---|
| Store card / bill / payment proof (staff web and mobile) | `POST /compliance/upload` → `compliance_service.upload` → `_prepare` → `save_document` | `[Bills/ or Payments/]<Month Year>/<STATE>/<ENTITY>/<code>-<kind>-v<N>-<random>.<ext>` | `compliance_documents` + `_versions` | `GET /compliance/{id}/url` (fresh 300 s signed link, browser loads straight from Tigris); fallback `/file` | store assigned to the employee, or `compliance.manage` / `accounts.view` |
| Bulk upload (admin) | `POST /compliance/bulk` | same | same | same | `compliance.upload` / `compliance.manage` |
| Vendor / POC documents | `POST /external/documents` (same `_prepare`) | same | same | `GET /external/documents/{id}/file` (streamed) | the account's own stores |
| Cash purchase proof | `POST /cash-purchases` → `cash_purchase_service.create` | `Cash purchases/<YYYY-MM>/<purchase id>.<ext>` | `cash_purchases.proof_*` | `GET /cash-purchases/{id}/proof` (streamed; the web app uses a temporary blob URL) | `cash.view` sees all; `cash.add` only their own (404 otherwise) |
| Ticket / issue photos | `external_uploads.read_photos` + `store_photo` | `Tickets/<ticket id>/<random>.jpg` | `ticket_attachments` | `GET /tickets/{id}/attachments/{aid}` (staff), `/external/tickets/...` (vendor) | same rule as the ticket |
| Test reports | `POST /test-reports` | `Test reports/<platform>/<STATE>/<period>-v<N>.<ext>` | `test_reports` | `GET /test-reports/{id}/url` or `/file` | `orders.overview` to view, `compliance.manage` to upload |
| Store images | none: the store model has no image or file column | | | | |

`scripts/migrate_storage.py` (local → bucket copy; deletes local files only with `--delete-local`) covers compliance documents only, not versions, cash proofs, tickets or test reports. The audit script (section 6) shows whether anything still says `local`.

## 3. Findings and what was changed

### Critical
None: no code path could delete or expose existing data.

### High (fixed)
- **F1. Uploads froze the server.** `compliance.upload`, `compliance.bulk`, `cash_purchases.create`, `test_reports.upload` were `async def` doing blocking work (S3 write, database, image merge) on the event loop. They are now plain functions that FastAPI runs on worker threads.
- **F2. Photos were stored at full size**, up to 12 MB, with GPS included. Now: resized to 1,600 px, made upright, metadata and GPS stripped, stored as JPEG (PNG only with real transparency), **always at most `PHOTO_MAX_STORED_KB` (1,024 KB)**: if the first attempt is larger, quality and then size are lowered step by step until it fits, and a photo that cannot fit is refused with a message (nothing stored). An already-small, GPS-free image is left byte-for-byte as it is; a second pass never recompresses. PDFs are never touched. Merged-photo PDFs are shrunk until they fit the PDF limit.
- **F3. Two simultaneous uploads for the same store, month and kind could overwrite each other's file** (the key held only the version number). Keys now carry a random suffix; existing keys are unchanged.
- **F10. A write was trusted without being checked.** `save_verified` now re-reads the stored size (one HEAD) after every write and raises if the store did not confirm exactly those bytes; the database record is created only after that. A failure answers **503 "The file could not be saved right now and nothing was recorded"** with `Retry-After`, and no record exists. Nothing is ever deleted on failure.
- **F11. A retried upload could create a second version.** `/compliance/upload` now honours `Idempotency-Key` (cash and vendor uploads already did): a resend after a lost response returns the first result. The web app now sends one key per selection of files, so clicking Upload again after a lost response is safe; the server side works for every client.

### Medium
- **F4.** Truncated but correctly headed images were stored undecoded; now refused with a clear message.
- **F6.** PDF cap separated from the photo limit (see section 0).
- **F7.** Order of operations is safe in every path: the object is written and confirmed first, the record second. If the database fails after a confirmed write, one unreferenced object remains (harmless); the audit lists it as an orphan **candidate** after a grace period and never removes it.
- **F8. Dead configuration:** `MAX_UPLOAD_SIZE_MB = 8` and `ALLOWED_UPLOAD_CONTENT_TYPES` are not read anywhere; they suggest limits that do not exist. Left alone.
- **F9. Fly holds two sets of storage keys** (`AWS_*` and `S3_*`, different fingerprints) and `STORAGE_BACKEND` is set in `fly.toml` and as a secret. The app reads `S3_*`. Check the other pair is not an unused extra credential.
- **F12. Monitoring was absent.** Added structured log lines (never a link or secret): `file stored` (category, key, size), `storage write failed`, `storage write not confirmed`, `stored file missing` (table, record id) on every read path, and a daily `storage usage` line with **warnings at 80% of `STORAGE_QUOTA_GB` and above 100%, and on unusual weekly growth** (more than 3x the previous 4-week average and at least 100 MB). The quota setting is only a warning level; it is not enforced and pricing is not in the code.

### Low
- Cash receipts and ticket photos are streamed through the API (`exists` + `read`); at about 300 KB this is fine. Proxied images use `Cache-Control: private, no-store`, which is correct for private data.
- `/api/v1/ready` makes one bucket request per call; Fly's own check uses `/health` (no storage). Do not point an external monitor at `/ready` every minute (about 43,200 requests a month).
- The mobile app does not resize photos before sending (needs a native module and a new APK). The server shrinks them, so it works, but uploads on weak mobile data are larger than they need to be.

### Verified OK, no change needed
Authorization on every file route (store assignment, role, ownership; 403/404 for another store's or person's file); signed links are short-lived, fresh per open, never stored; the web app releases its temporary blob URLs; image previews are local (files just picked, read from the person's own device), never one request per list row; unreadable-object and permission errors are shown to the user by the API layer; the web app already refreshes expired links by asking again.

## 4. Direct browser-to-Tigris uploads: not implemented, on purpose

Tigris supports presigned PUT, but the server has to see each photo to shrink it, check its real type and enforce the 1 MB / 2 MB limits (that is where the cost control and the safety come from). Direct upload would move that to every browser and the mobile app, need bucket CORS, a two-step API and a pending-upload table, and the saving is tiny: about 1,950 files of ~0.3 MB is under 1 GB a month through Fly. The authenticated backend route is therefore kept, as your instructions allow. The "pending then available" state you describe is achieved inside one request: the file is written and confirmed, and only then is the record created, so an attachment is never "available" before it is verified. If volume grows, the design is: `POST /uploads/init` (auth, permission, size limit, 5-minute presigned PUT for a server-made key) → client PUT → `POST /uploads/complete` (server HEAD-verifies, then records).

## 5. Estimates

**Assumptions (yours, not measured):** 1,500 store images × 300 KB, 300 store PDFs × 500 KB, 100 cash images × 300 KB, 50 other attachments × 500 KB per month = **1,950 files, 655 MB a month**, all kept, nothing already stored. Decimal units: 1 GB = 1,000 MB (Tigris's own unit may be binary, which makes a GiB 7.4% larger). In this app these map to the monthly compliance documents (card, bill, payment proof) plus cash proofs and ticket files.

**Provider facts (tigrisdata.com/pricing.md, read 2026-10-17, single-region Standard):** free each month 5 GB storage, 10,000 Class A (PUT, COPY, POST, LIST), 100,000 Class B (GET, SELECT, all other including HEAD); beyond that storage $0.02/GB-month, Class A $0.005 per 1,000, Class B $0.0005 per 1,000; egress free; DELETE free. The page does not say how presigned-URL signing is billed; boto3 signs locally with no network call, so only the browser's GET reaches Tigris. Treat these as the quote at that date, not as constants.

| Month | Stored (projected) | Free storage left | Billable | Storage charge that month |
|---|---|---|---|---|
| 1 | 0.655 GB | 4.345 GB | 0 | $0.00 |
| 3 | 1.965 GB | 3.035 GB | 0 | $0.00 |
| 6 | 3.930 GB | 1.070 GB | 0 | $0.00 |
| **8 (first over 5 GB)** | 5.240 GB | -0.240 GB | 0.24 GB | $0.005 |
| 12 | 7.860 GB | -2.860 GB | 2.86 GB | $0.057 |

Storage charges added up over the whole first year: about **$0.15**. Projected only: compare with the Tigris dashboard and the `storage usage` log line.

**Requests per month (from the code):** an upload = 1 PUT (Class A) + 1 HEAD to confirm the write (Class B); a view = 1 HEAD + 1 GET (Class B). With 25 employees × 20 views × 22 days = 11,000 views:

| | Class A | of 10,000 free | Class B | of 100,000 free | Request charge |
|---|---|---|---|---|---|
| Normal month | 1,950 | 19.5% | 23,950 | 23.9% | $0.00 |
| If every PDF open made 3 range requests (uncertain; depends on the PDF viewer) | 1,950 | 19.5% | about 45,950 | 46% | $0.00 |

Class A would pass the free allowance at about 10,000 uploads a month; Class B at about 49,000 views a month. Exceeding an allowance never blocks anything; it is billed at the rates above (10,000 extra Class B requests cost $0.005).

**If photos averaged the full 1 MB cap instead of 300 KB** (the worst case the policy allows): about 1,775 MB a month, 21.3 GB after 12 months, over 5 GB in month 3, roughly $0.33 a month of storage by month 12. The optimizer's job is to stay near 300 KB: on a synthetic 12-megapixel receipt with small print it produced about 200 KB with the text equally sharp when zoomed (a real photo with more detail will be larger; measure with the first week of real uploads).

**Not included:** files already in the bucket (unknown until the audit runs), replaced versions (the app keeps every version, so heavy replacement grows storage faster than the table), temporary copies, provider overhead.

## 6. Checking what is really in production (read-only; needs your go-ahead)

I could not read production data from here. Run this on Fly; it changes nothing, deletes nothing and prints no link or secret:

```
cd backend
fly ssh console -C "python scripts/storage_audit.py --json /tmp/audit.json"
```

It reports references per table and the backend each row recorded (`local` vs `s3`), **referenced but missing** files, **size mismatches**, **unreferenced objects** (only those older than 14 days are called orphan candidates, never removed), the quota and growth watch, and storage by folder. It lists the bucket once (1 Class A request per 1,000 objects). Exit code 0 = clean, 1 = a broken reference was found.

## 7. Retention and data safety

- **Valid business files are kept indefinitely.** No expiry rule, no age-based or usage-based cleanup, no "orphan" removal exists anywhere in the application. A test scans the application source and fails if any code calls `storage.delete` or `delete_object`.
- Replacing a document adds a version; "remove" only archives; a failed or unconfirmed write leaves the previous file untouched.
- **No migration and no schema change** in this work: no row or object is touched; the new rules apply to new uploads only. Existing keys, links and records work unchanged.
- Any future move of legacy files must follow: dry-run report → verified backup and a test restore → copy (never move) → verify the destination → update references only after verification → keep the source through a rollback period → your approval before anything destructive. `scripts/migrate_storage.py --dry-run` already does the first steps for compliance documents.

## 8. Tests

Backend: `tests/test_storage_safety.py` and `tests/test_storage_policy.py` (S3 mocked with moto, local disk otherwise, test database). Frontend: `src/lib/uploads.test.ts`. They cover: valid image and PDF upload; several optional attachments on one store and a store with none; file above the maximum; invalid content or signature (judged by content, not name or declared type); truncated image; unauthenticated upload and download; another store's file and another person's receipt; Tigris unavailable (503, no record); database failure after a successful write (current file intact); interrupted upload and safe retry with the same key; a write the store does not confirm; lost response and resend; expired link (a new one is issued, never stored); files readable after a simulated restart; replacing keeps the old file and the new one obeys the limit; a missing object (clean 404 plus an alert log, no crash); the audit report deleting nothing and ignoring fresh uploads; quota and growth thresholds; no application code deletes files; endpoints not blocking the server; defaults and validation of the settings; the browser helper (PDF limit and advice, small photo untouched, large photo shrunk only if smaller, shrink failure falls back, several files report each problem).
I confirmed the tests can fail: with the optimizer, the size budget, the key suffix or the write confirmation disabled, the matching tests went red.
**Not testable here:** PDF preview and download on real phones and desktop viewers, "after a frontend redeployment" (the backend and files do not depend on the frontend build; confirm by opening one file after the next Vercel deploy), a real Tigris outage and real mobile networks. Use the checklist in section 12.

```
cd backend
.venv\Scripts\python.exe -m pytest tests/test_storage_safety.py tests/test_storage_policy.py -q
.venv\Scripts\python.exe -m pytest -q                     # everything
cd .. ; npx vitest run                                    # web
```

## 9. Settings (names only; never commit values)

Already on Fly: `STORAGE_BACKEND`, `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_URL_EXPIRE_SECONDS`.
New and optional (validated; defaults shown in `backend/.env.example`): `PHOTO_MAX_STORED_KB` (1024), `PDF_MAX_FILE_MB` (2), `COMPLIANCE_MAX_FILE_MB` (12, the raw-upload ceiling), `IMAGE_OPTIMIZE`, `IMAGE_MAX_DIMENSION` (1600), `IMAGE_JPEG_QUALITY` (80), `IMAGE_KEEP_BELOW_KB` (350), `STORAGE_QUOTA_GB` (5, warning level only), `STORAGE_WARN_PERCENT` (80). The web app reads the limits from `GET /api/v1/uploads/policy`.
The Tigris secret keys exist only on Fly. The browser never receives them; it receives only short-lived signed links for files it is allowed to open.

## 10. Backups and recovery (an honest picture)

A database backup alone does **not** protect uploaded files: Neon holds the keys and metadata, Tigris holds the bytes. Recovery needs both, taken close in time.
- **Neon:** point-in-time restore / branching; the window depends on your plan. Check it in the Neon console. Not enabled or paid for by this work.
- **Tigris:** the pricing page lists snapshots and forks; whether they are available and what they cost on your account is not verifiable from here. Enabling versioning or snapshots can raise storage cost, so it needs your approval; the alternative is a scheduled copy of the bucket to a second location.
- **A restored database must point at objects that still exist.** Because nothing deletes files and keys are unique, a restored database always finds its files; the audit script run right after a restore proves it (`referenced but missing: 0`).

## 11. What could not be verified, and how

| Item | How to check |
|---|---|
| Number of files, missing, orphaned, rows still saying `local` | `storage_audit.py` (section 6) |
| Bucket private, no lifecycle (auto-delete) rule | Tigris console → bucket settings |
| Which Fly key pair is in use; unused extra credential | Tigris console → access keys, compared with `fly secrets list` names |
| Neon restore window | Neon console → Restore |
| Tigris snapshots / versioning availability and cost | Tigris console and pricing; needs your approval |
| Size of real lab test-report PDFs | Look at 3-5 real ones; raise `PDF_MAX_FILE_MB` if they exceed 2 MB |
| PDF open on Android and iPhone | Open one PDF from the web app and from the app on each |

## 12. Checklists

**Before deploying:** full test suite green → `fly deploy` from `backend/` (no migration) → `/api/v1/ready` ready → run `storage_audit.py` → from a real phone upload one photo, one PDF and one cash receipt, open each from the web app → check the Fly logs show `file stored` lines and no `storage write failed`.
**Rollback:** `fly releases` then redeploy the previous image (or commit). There is no data to undo; files written by the new code are ordinary files the old code reads. The web app only needs the previous build if its upload screens misbehave (Vercel → Deployments → promote the previous one).
**Backup and restore verification (once, then monthly):**
1. Neon: create a restore point or branch, open it, count rows in `compliance_documents` and `cash_purchases`, compare with production, delete the branch.
2. Bucket: copy 10 keys from the audit output to another location, or open a snapshot/fork if you have enabled one; open each as a real image/PDF.
3. Run `storage_audit.py` against the restored database and confirm `referenced but missing: 0`.
4. Write down the date, the row counts and who checked.

## 13. Before Monday, and what can wait

**Before Monday:** deploy; run the audit and read "missing"; decide `PDF_MAX_FILE_MB` after looking at real PDFs; one real-phone upload of each kind; confirm a Neon restore window and a bucket backup plan.
**Can wait:** client-side resize in the mobile app (new APK; then `COMPLIANCE_MAX_FILE_MB` can drop to 1); signed links for cash receipts and ticket photos; direct-to-bucket uploads; removing the dead `MAX_UPLOAD_SIZE_MB`; free-form extra attachments per store (needs your decision and a migration).

## 14. Remaining risks

- Production file state is unknown until the audit runs.
- A real Tigris outage makes uploads answer 503 (nothing recorded) and downloads fail until it returns; there is no second storage location.
- PDFs above `PDF_MAX_FILE_MB` are refused; if bills or lab reports are routinely larger, employees will hit it on day one.
- The photo size cap depends on image detail: a very detailed photo may be refused with "take it again"; keep an eye on the first week of upload errors.
- Replaced versions are kept forever, so heavy replacement grows storage faster than the projection.
