# Veekay CRM — Backend (Phase 1)

FastAPI + PostgreSQL foundation: organizations (tenant/partner isolation),
users, roles, permissions, JWT auth with refresh rotation, failed-login
lockout, and an append-only audit log table.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set a real JWT_SECRET_KEY and DATABASE_URL

# create the database, then:
alembic upgrade head

uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for the interactive API docs.

## What's here

- `app/core/security.py` — the ONLY place passwords are hashed and JWTs
  are issued/verified.
- `app/api/deps.py` — the ONLY place "is this user allowed to do this"
  is decided (`require_permission(...)`, `require_same_organization(...)`).
  Every future route should depend on these rather than re-checking roles
  inline.
- `app/models/` — Organization, Role, Permission, User, UserRole,
  AuditLog. Orders/Tickets/Stores land here in Phase 3–4.
- `app/services/auth_service.py` — login/refresh/lockout business logic,
  kept out of the route layer so it's unit-testable without an HTTP layer.
- `alembic/versions/0001_phase1_foundation.py` — initial schema. Written
  by hand since there's no live Postgres to autogenerate against here;
  review it against your actual Postgres version before running.

## Seeding roles/permissions

Run this once after `alembic upgrade head`, before your first login:

```bash
python scripts/seed.py
```

It creates the `veekay` organization, `admin` and `employee` roles with a
starter permission set, and two users:

- `admin@veekay.com` / `ChangeMe123!` (admin role)
- `employee@veekay.com` / `ChangeMe123!` (employee role)

Change both passwords before this goes anywhere near production. Add more
roles (`super_admin`, `regional_manager`, `blinkit_admin`, `zepto_admin`,
...) the same way as usage grows (spec section 6).

## Not yet implemented (by design — later phases)

Employees CRUD, Orders, Tickets, Google Apps Script integration adapter,
Stores/Regions, partner exports, background jobs, rate limiting, file
upload handling, dashboard aggregation endpoints. The architecture
(service → repository, permission-based routes, organization scoping)
is meant to make all of these additive, not a rewrite.
