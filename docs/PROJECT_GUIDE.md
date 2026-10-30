# Veekay CRM / Aquatrack: the complete project guide

Everything about how this project is built, where each thing lives, and how each process (run, test, deploy, build the app) works.
Written 2026-10-29. Where something could not be checked from the code, it says **(not verified)**.

Contents: 1 The big picture · 2 Production map · 3 Folder map · 4 Backend · 5 Web app · 6 Phone app · 7 Business rules · 8 Step-by-step processes · 9 Operations and safety · 10 Known issues and cleanup log

---

## 1. The big picture

There are **three programs** that share **one database**:

```
 Employees' phones                 Office browsers                 Vendors / POCs
 (Aquatrack Android app)           (CRM web app)                   (vendor web portal + same Android app)
        |                                |                                |
        |   HTTPS + login token          |                                |
        +--------------------+-----------+--------------------------------+
                             v
                  BACKEND API  (FastAPI, Python)         <- the only thing that touches the data
                  runs on Fly.io, https://veekay-crm-api.fly.dev/api/v1
                     |                    |                       |
                PostgreSQL           File bucket (S3)        Outside services
                (all records)        (photos, PDFs,          Gmail SMTP (password-reset mail), Firebase (push
                                      store cards)           notifications), Google Sheets (optional daily sync)
```

* The **backend** holds all rules and all data. The web app and the phone app are only screens: they ask the backend and show the answer.
  So a rule (who may edit, which dates are open) is changed **once, in the backend**, and both apps obey it.
* The **web app** (React) is what office staff and admins use. It is hosted on **Vercel**, which also serves the Android installer file.
* The **phone app** (Aquatrack, built with Expo / React Native) is what field employees use to mark daily bottle counts, scan bottles, check in, etc.
* The **database** keeps everything: stores, daily entries, employees, attendance, documents (as records), audit history.

---

## 2. Production map (what is live and where)

| Thing | Where | How it changes |
|---|---|---|
| Backend API | Fly.io app `veekay-crm-api`, region `sin` (Singapore), 1 machine (2 shared CPUs, 1 GB RAM, 2 worker processes). `https://veekay-crm-api.fly.dev/api/v1`. Health: `/api/v1/health`, deeper check: `/api/v1/ready` | `fly deploy` from the `backend/` folder (section 8.3) |
| Web app | Vercel, `https://veekay-crm.vercel.app` | `git push` to the main branch: Vercel builds and publishes by itself (section 8.4) |
| Android installer + update notice | Same Vercel site: `public/downloads/*.apk` and `public/app-update.json` | You build the APK on this PC, run the publish script, then `git push` (section 8.5) |
| Database | PostgreSQL, connection string in the Fly secret `DATABASE_URL`. The provider and its backup plan are **(not verified)**: check the provider's dashboard | Schema changes ship as migrations that run automatically on each backend deploy |
| Files (photos, PDFs, cards) | A private S3-compatible bucket (the Fly-generated `AWS_*` / `BUCKET_NAME` secrets suggest Fly's Tigris storage). Browsers get a link that expires in 5 minutes; the API never streams the file | Settings are Fly secrets (`S3_*`, `STORAGE_BACKEND=s3`) |
| Password-reset email | Company Gmail account over SMTP (host and sender are in `backend/fly.toml`, password is the Fly secret `SMTP_PASSWORD`) | Fly secret |
| Push notifications | Firebase project `veekay-aquatech`; the key is the Fly secret `FIREBASE_CREDENTIALS_JSON`; the phone side is `mobile/google-services.json` (git-ignored, baked into the APK) | Secret + new APK |
| Source code | GitHub repository (branch `main`). CI (`.github/workflows/ci.yml`) runs on every push | `git commit` / `git push` |

**Fly secrets that exist** (names only; values are never in the repo): `DATABASE_URL`, `JWT_SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`, `AWS_*`, `BUCKET_NAME`,
`S3_*`, `STORAGE_BACKEND`, `CORS_ORIGINS`, `PUBLIC_APP_URL`, `REFRESH_COOKIE_SAMESITE`, `SMTP_PASSWORD`, `FIREBASE_CREDENTIALS_JSON`. List them with `fly secrets list` (run in `backend/`).
Plain (non-secret) settings live in `backend/fly.toml`.

Nothing deploys itself except the web app (Vercel on push). **The backend and the Android app are always shipped by hand.**

---

## 3. Folder map

```
veekay-crm/
├── src/                    WEB APP source (React + TypeScript)
│   ├── app/                  router (all page addresses), layout, home redirect
│   ├── components/           shared UI pieces (buttons, tables, layout, feedback states)
│   ├── features/             one folder per area: orders, attendance, entries, stores, tickets, cards,
│   │                         compliance, cash, payroll, capping, inventory, zero (zero-review), vendor (vendor portal), ...
│   ├── services/             the code that calls the backend (api.ts, auth.ts, orders.ts, ...)
│   ├── types/ hooks/ lib/    types, small hooks, helpers (csv export, formatting, ...)
│   └── main.tsx, index.css   entry point and global styles
├── public/                 files Vercel serves as-is
│   ├── app-update.json       THE UPDATE NOTICE phones read (latest version code, minimum, download link)
│   ├── downloads/            the published Android installer (.apk), newest only
│   ├── vendor/               the vendor portal's installable-web-app files (manifest, service worker, icons)
│   └── watr-logo.png, favicon.png, theme-init.js
├── index.html, vite.config.ts, tailwind.config.js, tsconfig*.json, eslint.config.js, vitest.config.ts   web build/tool settings
├── vercel.json             Vercel: build command, security headers, APK headers, route fallback
├── package.json            web app dependencies and commands (dev, build, test, lint)
│
├── backend/                BACKEND (Python / FastAPI)
│   ├── app/
│   │   ├── main.py           starts the API, adds the middleware, mounts all routes
│   │   ├── api/v1/endpoints/ the URL list (one file per area: orders.py, entries.py, attendance.py, auth.py, ...)
│   │   ├── api/deps.py       login + permission checks used by every route
│   │   ├── services/         ALL business rules (order_service, entry_service, performance_service, attendance_service, ...)
│   │   ├── models/           database tables (SQLAlchemy)
│   │   ├── schemas/          request/response shapes (Pydantic)
│   │   ├── repositories/     a few reusable database queries
│   │   └── core/             config.py (all settings), entry_access.py (who may see/edit entries),
│   │                         security.py (passwords, tokens), storage.py (files), scheduler.py (timed jobs),
│   │                         middleware.py, ratelimit.py, cache.py, mailer.py, roles.py
│   ├── alembic/versions/   database migrations, numbered 0001 ... 0061 (latest). Run in order on every deploy
│   ├── scripts/            seed.py (roles/permissions, runs every deploy), create_developer.py, create_external_accounts.py,
│   │                         reset_external_passwords.py, migrate_storage.py, storage_audit.py, store_count_check.py,
│   │                         clear_store_entries.py, benchmark.py, loadtest/   (maintenance tools, run by hand)
│   ├── tests/              ~67 test files (pytest, real PostgreSQL)
│   ├── Dockerfile, fly.toml  how the backend is packaged and run on Fly
│   ├── requirements.txt    runtime libraries;  requirements-dev.txt  adds test tools
│   ├── .env                YOUR LOCAL settings (git-ignored, never committed)
│   └── .venv/              local Python environment (git-ignored)
│
├── mobile/                 PHONE APP (Expo / React Native, Android)
│   ├── src/app/              screens (file name = screen). staff/ = employee app; the others = vendor / POC app
│   ├── src/api/ auth/ lib/ components/ theme.ts   server calls, sign-in, helpers, shared UI, colours
│   ├── app.config.ts         app name (Aquatrack), version, permissions, plugins, package id com.veekay.partner
│   ├── scripts/              build-local-apk.mjs (build), publish-release.mjs (publish), check-release.mjs, release-*.mjs
│   ├── build/apk/            finished installers on this PC (git-ignored)
│   ├── android/              generated native project (git-ignored, rebuilt on each build)
│   ├── google-services.json  Firebase key for push (git-ignored)
│   └── RELEASE.md, UPDATES.md, PLAY_STORE.md   detailed phone-release notes (kept, still accurate in the main)
│
├── docs/                   reference documents: this guide, how entry ownership and audit work (ENTRY_OWNERSHIP_AND_AUDIT.md),
│                           card audit, storage audit, Google-Script tickets, mobile launch/compliance, load-test results
├── DEPLOY_FLY_VERCEL.md    the original production launch checklist (generic; real URLs are in section 2 here)
├── .github/workflows/ci.yml  automatic checks on push (backend tests, web lint/test/build, security audits)
├── .easignore              upload filter for Expo cloud builds (only matters if you ever run an EAS cloud build)
├── skills-lock.json        record of coding-assistant skills installed for this repo (tooling only, not part of the app)
└── .claude/                coding-assistant settings (local)
```

Never committed on purpose (git-ignored): `.env` files, `node_modules`, `.venv`, `dist`, `android/`, `build/`, logs, `storage/`, `google-services.json`, the signing key.

---

## 4. Backend

**Stack:** Python 3.11, FastAPI (web framework), SQLAlchemy 2 (database), Alembic (migrations), PostgreSQL, Pydantic (validation), PyJWT + bcrypt (login),
APScheduler (timed jobs), boto3 (S3 files), ReportLab + PyMuPDF + Pillow (PDFs and images), openpyxl (Excel), Sentry (optional error reporting), firebase-admin (push).

**How a request flows:** phone/web → HTTPS → middleware (request id, CORS, rate limit, size limit, security headers, gzip) → **endpoint** (checks login and permission,
validates input) → **service** (the business rules) → **models** (database). Endpoints stay thin; rules live in `services/`. Every table row belongs to an organisation.

**Login and sessions:** short-lived access token (15 minutes) plus a rotating refresh token kept in an HttpOnly cookie (web) or secure storage (phone). Each login is a
server-side session, so "sign out" and "deactivate this person" take effect immediately. **Permissions are read from the database on every request**, never trusted from the token,
so changing someone's role applies on their very next tap.

**Who is who (roles and the four entry levels).** The entry system has four levels (all decided in `app/core/entry_access.py`):

| Level | Who | Entries |
|---|---|---|
| **L1 Employee** | role `employee` | marks daily counts for their own stores, sees every colleague's entry of those stores (read-only), and can change or clear any entry of their stores in the open dates. Every change is audited |
| **L2 Team Lead** | `employee` + role `team_lead` (and they have people who report to them) | sees and corrects their team's entries, verifies them; sees only their team's performance and attendance |
| **L3 Entry Reviewer** | role `entry_reviewer` | sees every entry in their scope (whole organisation or one platform), edits and finalises entries, reads full history |
| **L4 Administrator** | role `admin`, and the **developer** (hidden role) | everything; admins use their own correction tools. History can never be rewritten, not even by them (the database refuses) |

Other roles: `accountant` (accounts staff), `partner` (a Blinkit/Zepto platform login), vendor / POC external accounts (their own portal and login system), and a few custom admin roles.
Fine-grained permissions (like `orders.view`, `orders.mark`, `orders.overview`, `orders.correct`, `attendance.view`, `leave.review`, `entries.audit`, `activity.view`) are ticked per person
on the Team page. The list of all permissions is created by `scripts/seed.py`.

**The entry data model (the heart of the system).** One row in `order_entries` = one store on one date (unique), with the bottle count. The database itself (triggers, migrations 0052/0053)
stamps who created it and who last changed it, bumps a `version` on every change of the number, and appends every create/edit/clear to an **append-only history table** (`order_entry_events`)
that nothing can edit. The `version` is what the app uses: version 1 = never changed. A developer's *cash adjustment* sits on top of an entry and is hidden from everyone below administrators.
Verification state per entry: submitted (L1) → verified (L2) → reviewed (L3). Deleted rows are archived, not lost.

**Timed jobs** (`app/core/scheduler.py`, run inside the API process, guarded by a database lock so only one runs): every day at 10:00 India time one run does the store/orders sheet sync
(only if Google Sheets are configured: **not verified** whether they are), sends the **bill-due reminders to vendors and POCs**, and writes one storage-usage line to the log;
a nightly audit-log purge runs at 03:30.

**Settings** are in `app/core/config.py` (every setting, with defaults). In production they come from `fly.toml` (plain) and Fly secrets (private). The app **refuses to start** in production
if the secret key is weak, CORS/URLs point to localhost, DEBUG is on, or S3 is chosen without credentials. Important ones: `BACKMONTH_GRACE_DAYS` (5), `MAX_BOTTLE_COUNT` (300),
`EMPLOYEE_CAN_CORRECT_OWN` (only matters for non-L1 accounts), `STORE_SYNC_HOUR`, `STORAGE_BACKEND`.

**Migrations (`backend/alembic/versions`).** Numbered files that change the database shape. Latest is **0061**. They only go forward. They run automatically at the start of each `fly deploy`;
if one fails the deploy stops and the old version keeps running. After the migrations, `scripts/seed.py` runs too (it adds new permissions/roles; it creates demo data only when
`ENVIRONMENT` is not production).

**Tests:** `backend/tests`, about 67 files, run against a throwaway real PostgreSQL database `veekay_test` (dropped, rebuilt, migrated and seeded each run). Run with
`cd backend; .venv\Scripts\python -m pytest`. Never run two test runs at once (they share that database and give false failures). CI runs them on every push.

---

## 5. Web app

**Stack:** React 19, TypeScript, Vite (build tool), Tailwind CSS (styling), TanStack Query (data fetching and caching), React Router, Zod. No Redux: server data lives in TanStack Query.

**How it is organised:** `src/app/router.tsx` lists every page address and which permission it needs (`<Require permission="...">`). Each area is a folder in `src/features/`.
`src/services/*.ts` are the only code that talks to the backend; the backend address comes from `VITE_API_BASE_URL` (on Vercel it is set in the project settings; locally the dev server forwards `/api` to `localhost:8000`).
The sidebar (`components/layout/AppLayout.tsx`) shows only the pages the signed-in person has permission for.

**Main pages:** Dashboard · Orders (mark, daily overview, performance, pending, correct) · Team entries and Store audit (entry review) · Attendance · Stores and Regions ·
Tickets · Cards and Compliance · Cash purchases · Payroll · Capping · Inventory · Reports · Team (employees and permissions) · Audit log (Activity and Entries by employee) ·
Zero review · Delivery reports · Data sync (developer) · plus the **vendor portal** at `/vendor/*` (separate login for vendors/POCs).

**Checks:** `npm run build` (this is the real type-check: it runs `tsc -b`, then Vite). `npx tsc --noEmit` at the root checks nothing because of the project layout, so do not trust it.
`npm test` runs the unit tests (Vitest). `npm run lint` runs ESLint.

---

## 6. Phone app (Aquatrack)

**Stack:** Expo SDK 57, React Native 0.86, TypeScript, expo-router (screens are files), TanStack Query. Package id `com.veekay.partner`; display name **Aquatrack**.
One app, two modes decided at sign-in: **staff** (employees, under `src/app/staff/`) and **vendor / POC** (the other screens).

**Staff screens:** Today, Orders (mark daily counts, with the calendar and colours), Scan bottles (works offline and syncs later), Compliance, Expenses, Attendance check-in, Leave, Payslips,
Inventory, My performance (new), Vendor performance, Alerts, Profile, and the Admin tab for people with admin permissions (insights, performance, attendance, leave approvals, bottles, pending stores).
The tabs shown depend on the person's permissions, read from the server at sign-in.

**Important idea:** the app is only a client. Rules such as "which dates are open" or "who may edit" are enforced by the backend. A change to the backend rule works for phones that are
already installed. A change to a **screen** needs a **new APK**.

**Update system.** The app reads `https://veekay-crm.vercel.app/app-update.json` when it opens. It contains the newest version code, the **minimum** version code, the download link and notes:
* installed < newest → "An update is available" (they can tap Later);
* installed < minimum → a full-screen "Update required" until they update;
* Android never installs silently: the person taps the downloaded file and accepts Android's own prompt.
**Rule you set: keep the minimum where it is** unless you explicitly decide to force a specific build (currently 18). Forcing locks out every phone below it.
OTA updates through Expo exist in the project (`expo-updates`) but, per `mobile/RELEASE.md`, that path **has not been used**; every app change goes out as a new APK.

**The signing key (critical).** Every APK must be signed with the same private key, or phones refuse the update and the app must be uninstalled (losing unsent offline scans).
It lives outside the repo in `%USERPROFILE%\.veekay-signing\` (`veekay-release.jks` + `keystore.properties`). **Back it up in two places.** Also keep the same package id and ever-higher version codes.

---

## 7. Business rules cheat-sheet

* **Marking window:** an employee can mark or change entries in **the current month, plus last month until the 5th** of this month (`BACKMONTH_GRACE_DAYS = 5`). On the 6th, last month closes for L1;
  older months are never open to L1. Future dates are never allowed. Admins can mark any past date. Beyond the window an employee can still **see** everything, but marking is switched off in both apps.
* **Who can change an entry:** every L1 can change/clear any entry of their stores inside the window (audited, first number kept in history). L2 corrects their team's `submitted` entries.
  L3 edits and finalises. L4 anything. Nobody can erase history.
* **Calendar colours** (set by the server, so web and phone agree): green = a Data Entry person's first entry; yellow = changed once; red = changed twice or more;
  blue = Team Lead's; violet = Reviewer / Admin / Developer.
* **Performance %:** for each employee, (store-days that have an entry) ÷ (every live store in their scope × every finished day this month). A day counts only after it is over. **Holidays play no part:** they belong to attendance; an entry dated on a holiday counts and declaring or changing a holiday never changes a count. Who entered an entry (the employee, a colleague, a spreadsheet upload by the Developer User) never decides whether it counts either.
  Colours: **green only at 100%**, yellow 99.9% down to 70%, red below 70%. A day one entry short never rounds up to 100.
  Who sees what: L1 only themselves, Team Lead only their team, admins/reviewers/overview-holders everyone. Click a day to see every store still missing days from the 1st up to that day; click a store to mark it.
* **Audit log (web):** the *Activity* tab lists every change in the workspace. The *Entries by employee* tab counts, per person, how many of their entries were never changed, changed once, or changed more than once,
  with the entries themselves one click away. *Store audit* and the per-entry history are for reviewers and admins.
* **Attendance:** check-in/out with the phone's location compared to the office (100 m). A Team Lead sees and approves only their team. Admins are not tracked.
* **Cards and compliance:** one document per store × month × kind (card, bill, payment); photos are merged into a PDF; the QR on a card opens a public page that shows month totals only.

---

## 8. Step-by-step processes

### 8.1 Run everything on your PC (development)
1. Start PostgreSQL locally (the dev database is `veekayCRM`; the connection is in `backend/.env`).
2. Backend: `cd backend; .venv\Scripts\activate; alembic upgrade head; python scripts/seed.py; uvicorn app.main:app --reload` → API on `http://localhost:8000` (docs at `/docs` in development).
   The seed creates demo logins in development only: `ADMIN001`, `DEV001`, `EMP001`, `EMP002` (password `Pass@123`). These are **never created in production**.
3. Web: from the repo root `npm install` once, then `npm run dev` → `http://localhost:5174`. It forwards `/api` to the backend.
4. Phone app: from `mobile/`, `npm ci` (this uses `mobile/.npmrc`, which is required), then `npx expo start` with a development build, or build an APK (8.5). Its server address is `EXPO_PUBLIC_API_URL` in `mobile/.env`
   (must end with `/api/v1`; the build refuses it otherwise).

### 8.2 Make a change safely
1. Edit code. 2. Backend: run the relevant tests (`.venv\Scripts\python -m pytest tests\test_xxx.py`), then the full suite before a deploy. 3. Web: `npm run build` and `npm test`.
4. Phone: `cd mobile; npm run typecheck; npm test`. 5. If you added a database column/table, write a new migration in `backend/alembic/versions` (never edit an old one). 6. Commit.

### 8.3 Deploy the backend (Fly)
1. `cd backend` (the folder with `fly.toml`). 2. Make sure you are logged in: `fly auth whoami` (if not, `fly auth login`).
3. `fly deploy`. Fly builds the image, then runs the **release command** (`alembic upgrade head` then `scripts/seed.py`) on a temporary machine. If it fails, nothing changes. Then it swaps the running machine and waits for the health check.
4. Check: `fly releases` (newest shows "complete"), `https://veekay-crm-api.fly.dev/api/v1/health` returns ok.
5. **Roll back:** `fly releases`, then `fly deploy --image <previous image>`. Migrations are forward-only, so a rollback of code does not undo a database change.
6. **If Fly's own API fails** (503/504, "failed to set release status", "missing third-party discharge token"): that is Fly, not your code. The old version keeps serving. Retry later; if it is an auth error, run `fly auth login`. You can retry with `fly deploy --image <the image it already built>` to skip rebuilding.
Secrets: `fly secrets set NAME=value` restarts the app (never put secrets in `fly.toml` or the repo). Always keep exactly **one** machine (the in-memory rate limits and the timed jobs assume it).

### 8.4 Deploy the web app (Vercel)
Commit and `git push` to `main`. Vercel runs `npm run build` and publishes. Nothing else to do. The backend must already be deployed if the web change uses a new backend feature (the web calls the live API).
Vercel also serves everything in `public/`, so pushing a new `public/app-update.json` + APK is what releases a phone update.

### 8.5 Build and publish a new Android APK
1. Change the code (JS-only changes keep the same `version` in `mobile/app.config.ts`; changes to native packages, permissions or app config need a new `version`).
2. `cd mobile; npm run typecheck; npm test`.
3. Build: `ANDROID_VERSION_CODE=<next number> npm run build:apk-local` (PowerShell: `$env:ANDROID_VERSION_CODE=31; npm run build:apk-local`). 20 to 30 minutes. It regenerates the native project, signs with your key and writes
   `mobile/build/apk/Aquatrack-<version>-code<N>.apk`. The number must be higher than the last published one (see `public/app-update.json`).
4. Publish locally: `npm run release:publish -- --min 18 --notes "What changed"`. This copies the APK into `public/downloads/` (only the newest is kept), writes `public/app-update.json` with the size and SHA-256, and checks the version. **Always pass `--min` with the current minimum** so nobody is forced.
5. `git add -A`, commit, `git push`. When Vercel finishes, phones see the update. Verify: `curl -sI https://veekay-crm.vercel.app/downloads/<file>.apk` (expect 200 and about 55 MB).
6. Test on one real phone first when you can (no emulator works on this PC). If the PC's C: drive is short on space (builds need about 4 GB free), the build folders are moved to `D:\veekay-build` through folder junctions (see `mobile/RELEASE.md`).
Needs on this PC: JDK 17 (at `%USERPROFILE%\.veekay-jdk17`), the Android SDK, the signing key, `mobile/.env`, `mobile/google-services.json`. If a build fails, run `mobile\android\gradlew.bat --stop` to end leftover Gradle processes.

### 8.6 Change the database
Create the next numbered file in `backend/alembic/versions` (copy the style of a recent one, set `down_revision` to the previous number). Add a test. Deploy the backend: the migration runs automatically before the new code goes live.

### 8.7 Add a permission or role
Add the permission code and description to the list in `backend/scripts/seed.py`; use `require_permission("code")` on the endpoint (backend) and `<Require permission="code">` on the route / `hasPermission("code")` in the screens.
`seed.py` creates it on the next deploy; then tick it per person on the Team page (or give it to a role in the seed).

### 8.8 Create the first admin on a fresh production database
Set the Fly secret `BOOTSTRAP_ADMIN_PASSWORD` (12+ characters); the seed creates `ADMIN001` with it, and that person must change it at first sign-in. Remove the secret afterwards (`fly secrets unset BOOTSTRAP_ADMIN_PASSWORD`).

---

## 9. Operations and safety

* **Monitoring:** point an uptime monitor at `https://veekay-crm-api.fly.dev/api/v1/ready` (returns 503 if the database, migrations or file storage is unhealthy). Set `SENTRY_DSN` for error reports (each error response carries a request id; search the logs for it: `fly logs`).
* **Backups:** the database provider's daily backups and a tested restore are **(not verified)**; confirm both. Files are in the bucket, not on the server, so a redeploy loses nothing.
* **Secrets you must never rotate casually:** `QR_SIGNING_SECRET` (invalidates every printed card QR). Rotating `JWT_SECRET_KEY` only signs everyone out (safe if it leaked).
* **Never lose:** the Android signing key folder; `backend/.env` is local only.
* **Scaling limits (fine for now):** the rate limiter, login throttle and read cache are per process; scheduled jobs assume a single machine. Revisit if you run several machines, see sustained slowness over 1 second, or database CPU above 70%.
* **A locked-out user:** an admin can reset their password on the Team page; locks also expire by themselves.
* **Data hygiene:** deleted rows are archived; entry history is append-only; a cleared entry stays visible in the audit trail.

---

## 10. Known issues and cleanup log

**Known issues (not fixed, for your awareness)**
* `npm run lint` reports 16 style errors in 6 older files (React "fast refresh" export rules and set-state-in-effect rules). CI runs lint, so check whether the CI badge on GitHub is red.
* The daily sheet sync only does something if the Google Sheet settings are configured on Fly. They do not appear in the secrets list, so it is probably off (the bill reminders in the same daily run still go out).
* `docs/CARDS_AUDIT.md` and `docs/STORAGE_AUDIT.md` are past audit reports; they describe the system as it was then.
* The Android install-over-the-top and the update flow have not been confirmed on a real phone (no device/emulator on this PC).

**Cleanup done on 2026-10-29** (everything removed is either git-ignored/regenerable or tracked in git history, so `git checkout -- <path>` brings back any file)
* Removed leftover logs from the repo root and `backend/` (`be.log`, `fe.log`, `ext.log`, `gradle_build.log`, `pytest_full.log`, `release_build27-30.log`, `fly-deploy-retry.log`, `build-local.log`, ...), all `__pycache__` folders and `.pytest_cache`, the local test uploads in `backend/storage`, and the web `dist` output.
* Removed one-off screenshot tools `capture_light.mjs`, `theme-audit.mjs` and the 30 generated images in `screenshots/` (nothing referenced them).
* Removed the Render hosting files `render.yaml` and `DEPLOY.md` (production runs on Fly + Vercel; the still-useful monitoring/operations notes are in section 9 above).
* Removed the stray root `app.json` (an old Expo config with a different EAS project id; the real one is `mobile/app.config.ts`), the unused web component `DemoDataBanner.tsx`, and three unreferenced public files (`Watr logo-1.png`, `icons.svg`, `favicon.svg`).
* Replaced the unedited Vite-template `README.md`, the outdated `ARCHITECTURE.md` and the "Phase 1" `backend/README.md` with short, accurate pointers to this guide.
* Kept on purpose: `docs/`, the backend maintenance scripts, `skills-lock.json`, `.easignore`, `DEPLOY_FLY_VERCEL.md`, and everything the apps or builds use.
