# Deploying Veekay CRM to Render

This repo ships a [`render.yaml`](./render.yaml) Blueprint that provisions everything:

| Resource      | What it is                          |
| ------------- | ----------------------------------- |
| `veekay-db`   | Managed PostgreSQL (free plan)      |
| `veekay-api`  | FastAPI service — runs `alembic upgrade head` + `scripts/seed.py` on every deploy |
| `veekay-web`  | The Vite build, served as a static site |

## 1. Push the repo to GitHub

```bash
git remote add origin https://github.com/<you>/veekay-crm.git
git push -u origin main
```

(or `gh repo create veekay-crm --private --source . --push`)

## 2. Create the Blueprint on Render

1. Render dashboard → **New → Blueprint**.
2. Connect the GitHub repo. Render reads `render.yaml` and shows the 3 resources.
3. Click **Apply**. First build takes a few minutes.
   - `JWT_SECRET_KEY` is generated automatically.
   - `DATABASE_URL` is wired from `veekay-db` automatically.

## 3. Fill in the two cross-reference values

These reference URLs that don't exist until step 2 finishes, so they start blank.
Once both services show a URL (e.g. `https://veekay-api.onrender.com` and
`https://veekay-web.onrender.com`):

| Service      | Env var             | Set to                                          |
| ------------ | ------------------- | ----------------------------------------------- |
| `veekay-api` | `CORS_ORIGINS`      | `["https://veekay-web.onrender.com"]`           |
| `veekay-web` | `VITE_API_BASE_URL` | `https://veekay-api.onrender.com/api/v1`        |

Use the **actual** URLs Render assigned (the name may have a random suffix if
`veekay-api` / `veekay-web` was taken).

Then **Manual Deploy → Deploy latest commit** on both services (the web app must
rebuild so the new `VITE_API_BASE_URL` is baked into the bundle).

## 4. Log in

Open the `veekay-web` URL. The seed script created:

- `admin@veekay.com` / `ChangeMe123!` — organization `veekay`
- `employee@veekay.com` / `ChangeMe123!`

**Change these passwords immediately** (or edit `backend/scripts/seed.py` before
deploying).

## Notes

- Free Postgres on Render expires after 30 days — upgrade the plan for anything
  real.
- Free web services sleep after 15 min idle; the first request after that is slow.
- `seed.py` is idempotent, so re-running it on each deploy is safe.
- Local dev is unchanged: `npm run dev` + `uvicorn app.main:app --reload`.


## Uploaded files (compliance cards & bills)

Cards and bills are stored on the API server's disk under `UPLOAD_DIR` (default `storage/`).
On Render's free plan that disk is **ephemeral** — files are lost on every deploy or restart.
Before real use, either:

- attach a persistent disk to `veekay-api` (paid plan), mount it at `/var/data`, and set
  `UPLOAD_DIR=/var/data/uploads`; or
- replace `backend/app/core/storage.py` with an object-storage version (S3, Drive, ...). It is
  the only file that touches the disk — everything else uses opaque keys.

## Vendor cards

Set `PUBLIC_APP_URL` to the web app's URL so the QR codes printed on cards open the right site,
and optionally `COMPANY_EMAIL` (shown in the card header). Re-run the seed on deploy (it already is)
so the new permissions and the `accountant` role exist.


## Signing in for the first time (production)

Production never creates demo users. On the first deploy:

1. Set `BOOTSTRAP_ADMIN_PASSWORD` on `veekay-api` to a strong one-off password (10+ characters, a letter and a number).
2. Deploy. The seed creates `ADMIN001` with it (only if no `ADMIN001` exists yet).
3. Sign in as `ADMIN001`. You'll be asked to choose your own password straight away.
4. Clear `BOOTSTRAP_ADMIN_PASSWORD` in the dashboard.

**If you already deployed an earlier version**, the demo accounts (`ADMIN001`, `EMP001`, `EMP002`, all with
password `Pass@123`) already exist in that database and the seed will not remove them. Sign in, open
**My account**, change `ADMIN001`'s password, then deactivate `EMP001` / `EMP002` on the Team page (or give them
new passwords with **Reset password**).

Also set `TRUST_PROXY_HEADERS=true` (already in `render.yaml`) so the failed-login limit uses each person's real IP.
