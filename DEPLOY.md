# Deploying and running Veekay CRM

`render.yaml` provisions everything on Render: `veekay-db` (PostgreSQL), `veekay-api` (FastAPI; runs
`alembic upgrade head` + `scripts/seed.py` on every deploy) and `veekay-web` (the Vite build as a static site).

## 1. First deploy

1. Push the repo to GitHub.
2. Render → **New → Blueprint** → pick the repo → **Apply**. `JWT_SECRET_KEY` and `DATABASE_URL` are wired automatically.
3. Fill in the values that depend on URLs which do not exist until step 2 finishes, then redeploy both services:

| Service      | Variable                  | Value                                                                 |
| ------------ | ------------------------- | --------------------------------------------------------------------- |
| `veekay-api` | `CORS_ORIGINS`            | `["https://<your-web-url>"]`                                          |
| `veekay-api` | `PUBLIC_APP_URL`          | `https://<your-web-url>` — **printed in every card's QR; set before printing** |
| `veekay-api` | `BOOTSTRAP_ADMIN_PASSWORD`| first admin password (≥ 12 chars). The admin must change it at first sign-in. Delete the value afterwards. |
| `veekay-api` | `COMPANY_EMAIL` (optional)| shown on the card header                                              |
| `veekay-web` | `VITE_API_BASE_URL`       | `https://<your-api-url>/api/v1`                                       |

Production never creates demo users. The first sign-in is `ADMIN001` with the bootstrap password.

## 2. Before real data goes in (do not skip)

* **Database backups.** Render's *free* Postgres expires after 30 days and has no backups. Use a paid plan
  (daily backups, point-in-time recovery) before entering real data. Also take a periodic `pg_dump` off-platform.
* **File storage.** Render's local disk is wiped on every deploy, so compliance documents would vanish. Either attach a
  persistent disk (paid) and set `UPLOAD_DIR`, **or** (recommended) use S3-compatible storage:
  1. Create a private bucket (AWS S3, Cloudflare R2, Backblaze B2…) and an access key limited to it.
  2. Set `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`
     (`S3_ENDPOINT_URL` for R2/B2; `S3_PREFIX` optional).
  3. Move any existing files: `python scripts/migrate_storage.py --dry-run`, then without `--dry-run`
     (`--delete-local` removes the local copies after a verified upload).
  The S3 backend is tested against a mocked S3 in CI; check one upload/view against your real provider after switching.
* **Plan.** Free web services sleep after 15 minutes idle; the first request afterwards is slow. Use a paid plan for staff use.

## 3. Monitoring and alerts

* **Uptime:** point an external monitor (UptimeRobot, Better Stack…) at `https://<api>/api/v1/ready`. It returns **503** when the
  database, migrations or file storage is unhealthy — so it alerts on real problems, not only a dead process.
  Render's own health check uses the cheap `/api/v1/health`.
* **Errors:** set `SENTRY_DSN` (and optionally `RELEASE`) — unhandled errors are reported with the request id.
* **Logs:** JSON lines in production, one per request with `request_id`, status and latency. Every error response returns
  a `request_id`; search the logs for it. Render → *Logs*, or add a log drain.

## 4. Operations

* **Deploys:** push to `main`; CI (`.github/workflows/ci.yml`) runs backend tests (real Postgres), `pip-audit`, frontend
  lint/tests/build and `npm audit`. Enable *branch protection* so a red CI blocks merging.
* **Rollback:** Render → *Deploys* → redeploy a previous build. Migrations are forward-only; write a new migration to undo schema changes.
* **Rotating `JWT_SECRET_KEY`:** signs everyone out (all tokens become invalid) — safe, do it if it may have leaked.
  Rotating `QR_SIGNING_SECRET` invalidates every printed QR — avoid.
* **A user is locked out:** an admin can reset their password (Team page); a lock also expires on its own.

## 5. Scaling notes (not needed yet)

One API instance comfortably serves a team of this size. Before running **more than one instance**, know that these are in-memory
per process: the rate limiter, the failed-login throttle and the attendance "last seen" throttle (limits become per-instance,
not global; nothing breaks). Scheduled jobs (APScheduler, e.g. store sync) would also run once per instance — move them to a single
worker/cron first. Triggers to revisit: sustained p95 latency > 1 s, DB CPU > 70 %, or > ~200 concurrent users; then add DB indexes
from `EXPLAIN`, a read replica, and Redis for shared throttling.
