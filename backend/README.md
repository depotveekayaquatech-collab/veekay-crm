# Veekay CRM: backend

FastAPI + PostgreSQL API. Full explanation (layers, roles, entry rules, deploy, tests): [../docs/PROJECT_GUIDE.md](../docs/PROJECT_GUIDE.md).

## Run locally

```bash
python -m venv .venv && .venv\Scripts\activate        # source .venv/bin/activate on Mac/Linux
pip install -r requirements-dev.txt
cp .env.example .env        # set DATABASE_URL and a long random JWT_SECRET_KEY
alembic upgrade head        # create / update the tables (migrations 0001 ... latest)
python scripts/seed.py      # permissions and roles; in development also demo logins ADMIN001 / DEV001 / EMP001 / EMP002 (password Pass@123)
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs` (switched off in production).

## Where things are

* `app/api/v1/endpoints/` the URL list; `app/api/deps.py` login and permission checks
* `app/services/` all business rules; `app/models/` tables; `app/schemas/` request/response shapes
* `app/core/` settings (`config.py`), who may see/edit entries (`entry_access.py`), files (`storage.py`), timed jobs (`scheduler.py`)
* `alembic/versions/` database migrations; `scripts/` maintenance tools; `tests/` pytest suite (real PostgreSQL, `veekay_test` is rebuilt each run)

## Vendor payments from Busy 21 (`POST /api/v1/busy-sync`)

The **Vendor payments** tab (every staff login, read only) shows, per vendor and month: month total (bills), paid, pending and closing balance. The data comes from Busy 21 by the API below (a script on the Busy PC will call it later) or by an administrator's CSV upload (**Vendor payments admin > Upload CSV**, with a column mapping and a dry run before anything is saved). The CRM never logs in to Busy.

* The **vendor code** is the only link: the same code ends the account name in Busy (`Sharma Traders Gurugram V0123`). Rows are matched by code, never by name. The format is the `BUSY_VENDOR_CODE_REGEX` setting (default `^V\d{4}$`, the last word of the name); the one function that reads it is `app/services/busy_codes.py`.
* A row whose code is not a CRM vendor is kept (with its raw row) under **Unmatched codes**, where an admin creates the vendor or maps the code to an existing one. Nothing is dropped.
* Permissions are computed per request: `vendorpay.view` for every non-partner staff login, `vendorpay.manage` for administrators and the developer only. The tab has no write endpoint; everything under `/vendor-payments/admin` needs `vendorpay.manage`.

Settings (environment): `BUSY_SYNC_API_KEY` (required to switch the endpoint on; set with `fly secrets set BUSY_SYNC_API_KEY=<long random value>`), `BUSY_VENDOR_CODE_REGEX`, `BUSY_STALE_HOURS` (default 6), `BUSY_SYNC_PER_MIN` (default 30 per IP), `BUSY_SYNC_MAX_ROWS` (default 20000 per request), `BUSY_CSV_MAX_MB` (default 5).

### Request

`POST /api/v1/busy-sync`, header `x-api-key: <BUSY_SYNC_API_KEY>`, JSON body:

```json
{
  "mode": "upsert",
  "period": {"from": "2026-10-01", "to": "2026-10-31"},
  "vendor_codes": ["V0456"],
  "entries": [
    {"account_name": "Sharma Traders Gurugram V0123", "date": "2026-10-03", "type": "BILL",
     "amount": "125000.00", "voucher_no": "PUR/0451", "narration": "Water bottles lot 1"},
    {"vendor_code": "V0123", "date": "2026-10-12", "type": "PAYMENT",
     "amount": 50000, "voucher_no": "PAY/0212", "narration": "Part payment"}
  ]
}
```

| Field | Notes |
|---|---|
| `mode` | `upsert` (default): add new entries, update edited ones. `replace_period`: also remove API-sent entries Busy no longer has (below). |
| `period` | `{from, to}` as `YYYY-MM-DD`. Required for `replace_period`; every entry must fall inside it (others are rejected). |
| `vendor_codes` | Optional, `replace_period` only: vendors to clear in the period even though they have no rows left in Busy. |
| `entries[].vendor_code` | Optional. When missing it is taken from the end of `account_name`. When both are given, `vendor_code` wins. |
| `entries[].date` | `YYYY-MM-DD` (`DD/MM/YYYY` and `DD-MM-YYYY` also accepted). A month is the entry's own calendar date. |
| `entries[].type` | `BILL` or `PAYMENT`. |
| `entries[].amount` | Positive, at most 2 decimals; a string is safest (money is never a float). |
| `entries[].voucher_no` | Required. With the vendor code and `type` it is the entry's identity: sending it again updates instead of duplicating. **Send one row per voucher per vendor per type** (add up several lines of one voucher); a repeat inside one request is rejected. |

`replace_period` removes entries that were **sent by the API** inside the period, for the vendors in the request (plus `vendor_codes`), that are not in the request, all in one transaction. Entries from a CSV upload are never removed by it.
Send `{"mode": "upsert", "entries": []}` as a heartbeat when nothing changed, so "Last updated" stays fresh. The page warns after `BUSY_STALE_HOURS` without a successful sync.

```bash
curl -X POST https://veekay-crm-api.fly.dev/api/v1/busy-sync   -H "x-api-key: $BUSY_SYNC_API_KEY" -H "Content-Type: application/json"   -d '{"mode":"upsert","entries":[{"vendor_code":"V0123","date":"2026-10-03","type":"BILL","amount":"125000.00","voucher_no":"PUR/0451"}]}'
```

### Response

`200` when the call was processed (also when some rows were rejected), `422` when every row was rejected or the body is malformed, `401` for a wrong or missing key, `429` when throttled, `503` while no key is configured.

```json
{
  "status": "PARTIAL", "dry_run": false, "log_id": "…",
  "received": 120, "inserted": 14, "updated": 3, "unchanged": 100, "deleted": 0, "unmatched": 2, "rejected": 1,
  "errors": [{"row": 7, "message": "type must be BILL or PAYMENT", "voucher_no": "PUR/0460"}],
  "errors_truncated": false, "unmatched_codes": ["V0777"], "sample": []
}
```

`row` is the 1-based position in `entries`. Valid rows are always processed, even when others are rejected. Every authenticated call writes a sync-history row (a wrong key writes only a log line, so strangers cannot fill the table); a database failure rolls the whole request back and is logged as `FAILED`.

### Run it

```bash
alembic upgrade head                 # migration 0063 creates the busy_* tables
python scripts/seed_busy_demo.py     # optional: 10 demo vendors V9001..V9010 and 3 months of entries (--remove deletes them)
```

## Deploy

`fly deploy` from this folder. It runs `alembic upgrade head` and `scripts/seed.py` as the release command before the new version goes live.
In production, demo users are never created; the first admin comes from the `BOOTSTRAP_ADMIN_PASSWORD` secret.
