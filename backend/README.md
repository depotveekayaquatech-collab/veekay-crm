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

## Deploy

`fly deploy` from this folder. It runs `alembic upgrade head` and `scripts/seed.py` as the release command before the new version goes live.
In production, demo users are never created; the first admin comes from the `BOOTSTRAP_ADMIN_PASSWORD` secret.
