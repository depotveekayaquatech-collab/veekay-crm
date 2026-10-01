# Architecture

```
Browser (React + Vite + TS + Tailwind, TanStack Query)
   │  HTTPS, Bearer access token (15 min) + rotating refresh token
   ▼
FastAPI  ── middleware (outer → inner): request id/logs · CORS · rate limit · body limit · security headers · gzip
   │  routes (app/api/v1/endpoints)  →  services (business rules)  →  repositories / SQLAlchemy models
   ├── PostgreSQL (Alembic migrations, head 0009)
   └── File storage: local disk or S3-compatible (app/core/storage.py)
```

## Layers of the backend
* **Endpoints** — thin: validate input (Pydantic), check permission, call a service.
* **Services** — all rules: orders/marking, compliance, attendance, monthwise virtual cards, auth/sessions.
* **Repositories/models** — queries and tables. Every table carries `organization_id`.

## Key decisions
* **Auth** — access JWT carries a `sid` (session) claim; each session is a `refresh_sessions` family on the server, so logout,
  "sign out everywhere" and deactivation take effect immediately. Refresh tokens rotate; reuse after a 15 s grace kills the family.
  Permissions are read from the database on every request (never trusted from the token).
* **Roles** — `admin`, `employee`, `accountant`; fine-grained permissions (`orders.*`, `compliance.*`, `accounts.*`, `attendance.*`).
  Staff categories (Admin / Accounts / Blinkit / Zepto employees) are derived in `app/core/roles.py`.
* **Attendance** — a sign-in of an employee/accountant starts a session row; the device location is read once, at login, and
  classified against the office (100 m default) with the haversine formula. Admins are never tracked.
* **Compliance** — one document per store × month × kind (`card`, `bill`, `payment`); photos are merged to PDF; content is sniffed, not trusted by name.
* **Virtual cards** — ReportLab PDF replicating the legacy Apps Script layout; the QR holds an HMAC-signed URL to a public page that shows month totals only.
* **Hardening** — security headers, per-IP rate limits (heavier on exports/uploads), request-size cap, API docs off in production,
  generic 500 body with a request id, bcrypt hashing, password policy, per-IP failed-login throttle, PyJWT (+ `pip-audit` in CI).

## Testing
`backend/tests` — pytest against a throwaway real PostgreSQL database (`veekay_test`, recreated, migrated and seeded each run):
passwords/tokens, auth/sessions, health/security, storage (local + mocked S3), attendance, compliance, cards.
`src/**/*.test.ts` — Vitest for frontend helpers. CI runs both plus lint, type-check, build and dependency audits.

## Known limits
Rate limiting and throttles are per process; the S3 backend has only been exercised against a mock; the *Test* report tab is a placeholder.
