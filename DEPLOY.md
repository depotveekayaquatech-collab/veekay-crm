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
