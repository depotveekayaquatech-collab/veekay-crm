# Production launch: API on Fly.io, frontend on Vercel

Layout: `https://crm.yourdomain.com` (Vercel, static SPA) calls `https://api.yourdomain.com` (Fly, FastAPI) directly.
Use two subdomains of one domain; large uploads (up to 150 MB) must go straight to Fly, not through a Vercel proxy.

## 0. Pre-launch checklist
- [ ] Commit everything (many files are only staged) and push to GitHub; CI green.
- [ ] Rotate any secret that was ever pasted in chat or committed. Never commit `backend/.env`.
- [ ] Managed Postgres with backups (Fly Managed Postgres, Neon or Supabase). Do not run unmanaged single-node Postgres for real data.
- [ ] S3-compatible bucket, **private**, with a key scoped to that bucket (Tigris on Fly is the easiest; see "1b. File storage"). Fly's disk is not durable across machines, so never use `STORAGE_BACKEND=local` in production.
- [ ] Domain with DNS you control.

## 1. Backend on Fly
```powershell
winget install flyctl          # or: iwr https://fly.io/install.ps1 -useb | iex
fly auth login
cd backend
# edit `app = ...` in fly.toml to a unique name, then:
fly launch --no-deploy --copy-config --name <your-app>
```
Database: create one (e.g. `fly mpg create`, or Neon/Supabase) and copy its connection string.

Set secrets (never put these in fly.toml):
```powershell
fly secrets set `
  DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB?sslmode=require" `
  JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" `
  CORS_ORIGINS='["https://crm.yourdomain.com"]' `
  PUBLIC_APP_URL="https://crm.yourdomain.com" `
  BOOTSTRAP_ADMIN_PASSWORD="<12+ chars, first admin only>" `
  S3_BUCKET=... S3_ENDPOINT_URL=... S3_REGION=auto S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... `
  TICKET_WEBHOOK_KEY="<random>" SENTRY_DSN="<optional>" `
  STORE_SYNC_SHEETS='["blinkit=SHEETID:0","zepto=SHEETID:0"]'
fly deploy
fly certs add api.yourdomain.com      # then add the DNS record Fly prints
fly scale count 1                     # keep ONE machine (see "Scaling" below)
```
The app **refuses to boot** in production if `JWT_SECRET_KEY` is weak, CORS/PUBLIC_APP_URL point to localhost or http, `DEBUG` is on, or S3 is selected without credentials. `fly logs` shows the reason.

Verify: `https://api.yourdomain.com/api/v1/ready` returns 200 and `/docs` returns 404.

Capacity is already set in `fly.toml`: a `shared-cpu-2x` machine with 1 GB RAM and `WEB_CONCURRENCY=2` (two API worker processes, one per core), because heavy pages are CPU-bound Python and one worker handles one request at a time. The cards, summary PDFs and photo merging (Pillow, PyMuPDF) also need the 1 GB.
```powershell
fly status                 # one machine, state "started", health check passing
fly logs                   # live logs; add --no-tail for a snapshot
```
Dashboard roll-ups and the admin store lists are cached for 30 s (`DASHBOARD_CACHE_SECONDS`). Every successful write bumps a counter in Postgres (`app_data_version`) that all workers and machines check, so a mark or correction shows up everywhere within about a second.

### 1b. File storage: how images are saved and served
Uploaded cards, invoices and payment proofs are **not** kept on the server. Each file goes to the bucket and the database stores only its **key** (a path such as `Bills/October 2026/Delhi/BCPL/…pdf`).
When someone clicks **View** / **Print**, the API checks their permission and returns a **signed link that expires in 5 minutes**; the browser then downloads the file straight from the bucket. The API server never streams the bytes, so downloads add almost no load to it.

Why a key and not a permanent URL: these are invoices and compliance documents, so a link that works forever for anyone would be a data leak, and a stored URL breaks whenever you change domain or bucket. The key never changes; the link is made fresh each time.

Create the bucket (Tigris, built into Fly; run from `backend/`):
```powershell
fly storage create          # pick your app; creates a PRIVATE bucket and sets AWS_* secrets on the app
```
It prints a bucket name, endpoint and access keys. Map them to the names this app reads:
```powershell
fly secrets set `
  STORAGE_BACKEND=s3 `
  S3_BUCKET="<bucket name>" `
  S3_ENDPOINT_URL="https://fly.storage.tigris.dev" `
  S3_REGION=auto `
  S3_ACCESS_KEY_ID="<access key id>" `
  S3_SECRET_ACCESS_KEY="<secret access key>" `
  S3_URL_EXPIRE_SECONDS=300
```
Cloudflare R2, AWS S3 or Backblaze B2 work the same way (just a different endpoint). Keep the bucket private.

If you already have files on a local disk or an old bucket, copy them over once with the same key layout (for example `aws s3 sync ./storage s3://<bucket>/veekay/ --endpoint-url <endpoint>`), then check a few documents with **View**.

Check it works: upload a document, press **View**; the new tab's address should start with your bucket's host and contain `X-Amz-Signature`. If View shows "file is missing from storage", the file was not copied to the bucket.

## 2. Frontend on Vercel
1. Vercel → Add New Project → import the repo (root directory = repo root; framework Vite; settings come from `vercel.json`).
2. Environment variable (Production): `VITE_API_BASE_URL = https://api.yourdomain.com/api/v1`
3. Deploy, then add the domain `crm.yourdomain.com`.
4. Tighten CSP once the domain is known: in `vercel.json` change `connect-src 'self' https:` to `connect-src 'self' https://api.yourdomain.com`.

## 3. First login and hardening
1. Sign in as `ADMIN001` with the bootstrap password, set a new password when prompted.
2. `fly secrets unset BOOTSTRAP_ADMIN_PASSWORD`.
3. Create real users on the Team page with least-privilege permissions.
4. Print vendor cards only after `PUBLIC_APP_URL` is correct (it is encoded in every QR code).
5. Uptime monitor on `/api/v1/ready`; set `SENTRY_DSN`.
6. Backups: confirm the DB provider's daily backups, and test one restore.
7. GitHub: enable branch protection requiring CI.

## 4. Security notes (what is already in place, and what to know)
In place: bcrypt + password policy, 15-minute access tokens, rotating refresh tokens with reuse detection, per-account lockout and per-IP throttle, permission checks on every route, tenant isolation, rate limits, body-size caps, upload content-type checks, security headers + HSTS, API docs disabled in production, no stack traces to clients, constant-time webhook-key check, `pip-audit` / `npm audit` in CI.

Session cookie: the web app keeps the refresh token in an **HttpOnly, Secure cookie** (JavaScript, and therefore any XSS, cannot read it). This needs the web app and API on the **same site** (e.g. `crm.yourdomain.com` + `api.yourdomain.com`). If you test with `*.vercel.app` + `*.fly.dev` (different sites), set `REFRESH_COOKIE_SAMESITE=none` on Fly, or browsers will drop the cookie.

Known trade-offs:
- **Rate limiting / the per-IP login throttle are in memory, per worker process.** With 2 workers an attacker effectively gets 2x the allowed attempts per IP (the per-account lockout is in the database and is exact). The daily sheet sync is safe on several workers and machines (Postgres advisory lock), and the read cache stays consistent across them. For exact throttling across workers/machines, add Redis later.
- Client IP is read from `Fly-Client-IP` (unforgeable on Fly). Don't put another proxy/CDN (e.g. Cloudflare orange-cloud) in front of the API without revisiting `TRUST_PROXY_HEADERS`.
- Google Sheets sync needs sheets shared "anyone with the link": treat that data as semi-public.

## 5. Deploy / rollback
- Deploy: `fly deploy` from `backend/` (runs `alembic upgrade head` first; a failed migration aborts the release). Frontend deploys on every push to `main`.
- Rollback: `fly releases` then `fly deploy --image <previous image>`; Vercel → Deployments → Promote a previous one. Migrations are forward-only.
- Rotate `JWT_SECRET_KEY` if leaked (signs everyone out). Never rotate `QR_SIGNING_SECRET` casually (invalidates printed QRs).

## 6. One-week plan before the team goes live
- **Day 1-2:** commit + push, CI green; create Fly app, managed Postgres, R2/S3 bucket; deploy to a *staging* Fly app + Vercel preview with the same steps (use a copy of real data, never the production DB).
- **Day 3:** click through every role (admin, employee, accountant, partner) on staging: login, cookie session survives refresh, logout, attendance check-in (needs https for geolocation), uploads, PDF/Excel exports, QR card scan, ticket webhook.
- **Day 4:** restore test: take a DB backup and restore it into a scratch DB; confirm files load from the bucket (View opens a signed bucket link). Set up uptime monitor + Sentry; trigger a test error.
- **Day 5:** load/abuse sanity: wrong passwords 6x (lockout), rapid requests (429), 9 MB upload (rejected), `/docs` is 404.
- **Day 6:** production deploy, bootstrap admin, remove `BOOTSTRAP_ADMIN_PASSWORD`, create team accounts, import stores/employees, print cards.
- **Day 7:** soft launch with 2-3 users, watch `fly logs` + Sentry, then everyone. Keep the previous release ready for rollback.
