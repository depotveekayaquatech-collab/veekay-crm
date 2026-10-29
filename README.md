# Veekay CRM / Aquatrack

Bottle-delivery operations for Veekay Aquatech: daily store entries, performance, attendance, compliance documents, cards, tickets, cash purchases and payroll.
Three programs share one database:

| Part | Folder | Stack | Hosted on |
|---|---|---|---|
| Backend API | `backend/` | Python, FastAPI, PostgreSQL | Fly.io (`veekay-crm-api`) |
| Web app (CRM + vendor portal) | `src/` (repo root) | React, TypeScript, Vite, Tailwind | Vercel |
| Android app (Aquatrack) | `mobile/` | Expo, React Native | built on a PC, served from the Vercel site |

**Start here: [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)**: what lives where, how everything works, and step-by-step processes (run, test, deploy, build the app).

Quick commands

```bash
# web app (repo root)
npm install && npm run dev        # http://localhost:5174, forwards /api to the backend
npm run build                     # the real type-check + production build
npm test                          # unit tests

# backend (backend/)
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements-dev.txt
alembic upgrade head && python scripts/seed.py
uvicorn app.main:app --reload     # http://localhost:8000
python -m pytest                  # needs a local PostgreSQL

# phone app (mobile/)
npm ci && npm run typecheck && npm test
npm run build:apk-local           # signed APK in mobile/build/apk (see mobile/RELEASE.md)
```

Deploying: backend `cd backend && fly deploy`; web: push to `main` (Vercel); Android: build, `npm run release:publish -- --min <current minimum> --notes "..."`, then push.
