# Launching the mobile app for testers

The code is ready. This is the order to do things in when you set up the server and database. For the server itself follow
[`DEPLOY.md`](../DEPLOY.md); this page covers what is specific to the app, in the order it matters.

## 0. What "synced" means here

There is one source of truth: the CRM database behind the API. The web app, the employee app, the POC app and the vendor app
all read and write it through the same API, so nothing has to be copied between them. The only thing that *brings data in* is
the sheet sync (stores, then order counts), which runs **every day at 10:00 IST** and on request. A test
(`backend/tests/test_everything_linked.py`) follows one store through marking, tickets, deliveries, scans and documents and
checks every role sees the same facts.

## 1. Server and database (do this first)

1. Deploy as in `DEPLOY.md` (`alembic upgrade head` runs on every deploy; the app needs migrations up to **0032**).
2. **Set `SYNC_TRIGGER_KEY`** (a long random string) and schedule the 10:00 sync from outside:
   - The API's own scheduler lives inside the API process. **On a free / sleeping plan that process is asleep at 10:00, so the daily sync would silently not run.**
   - Create a cron job at **10:00 IST (04:30 UTC)** that calls `POST https://<api>/api/v1/sync/trigger` with header `X-Sync-Key: <your key>`. Render Cron Jobs or cron-job.org both work. It wakes the server, runs the sync once (a second call within 30 minutes does nothing), and records it.
   - Or use an always-on paid plan and skip the cron; the in-process scheduler then runs it.
   - The same daily 10:00 run also sends the **bill-due reminders** to vendors and POCs (3 days before a bill is due, on the due date, and when it is 7, 14 and 30 days late; each reminder once per bill). So keep the 10:00 run going even if you have no sheets configured yet.
3. Set `STORE_SYNC_SHEETS` and `ORDER_SYNC_SHEETS` (see `backend/.env.example`). Check `GET /api/v1/sync/status` shows your sheets and a next run.
4. Real file storage (`STORAGE_BACKEND=s3`) and paid Postgres with backups, as `DEPLOY.md` says. **Ticket photos, bills and payment proofs from the app are stored there.**
5. First admin: `ADMIN001` with `BOOTSTRAP_ADMIN_PASSWORD` (production creates no demo users).
6. Create the vendor / POC logins on the new database: `python scripts/create_external_accounts.py --platform all`.
   Employees are added on the web **Team** page.
7. Smoke test the API: `https://<api>/api/v1/ready` must say ready; sign in on the web app; open **Data sync** and press **Sync now** once.

## 2. Passwords (before anyone outside the company signs in)

New vendor / POC logins start with predictable passwords (`123456` for vendors, `<name>@123` for POCs), and the logins are
guessable (`name@supplier.com`). **Replace them before launch:**

```bash
cd backend
python scripts/reset_external_passwords.py --only-default --dry-run              # how many
python scripts/reset_external_passwords.py --emails-file beta.txt --out beta.csv  # just your beta group
python scripts/reset_external_passwords.py --only-default --out all.csv           # everyone, when you go wide
```

The CSV holds `login,password,name,phone`. Send each person their own line (WhatsApp / SMS), then delete the file: passwords
exist nowhere else. One person later: web app → **Users & access → Logins →** pick them → **Set password** (it also signs
them out of old phones and clears a lockout).

## 3. Build the app

```bash
cd mobile
npx eas-cli login
npx eas-cli env:create --name EXPO_PUBLIC_API_URL --value https://<api>/api/v1 --environment preview --visibility plaintext
npx eas-cli env:create --name EXPO_PUBLIC_API_URL --value https://<api>/api/v1 --environment production --visibility plaintext
# also EXPO_PUBLIC_PRIVACY_URL, EXPO_PUBLIC_SUPPORT_EMAIL, EXPO_PUBLIC_SUPPORT_PHONE for both environments
npm run build:apk        # a test build you can send as a link: testers install it directly (they allow "install unknown apps")
npm run build:aab        # the Play Store build
```

Push messages need Firebase (`mobile/README.md`); leave it for later if you like: alerts then show inside the app.

## 4. Get it to testers

| Route | Good for | Notes |
|---|---|---|
| **EAS preview APK link** | the first 5–10 people, today | no store needed; Android only; update by sending a new link |
| **Play *Internal testing*** | up to 100 named testers | add their Gmail addresses; they install from the Play Store; no review wait |
| **Play *Closed testing*** then **Production** | the real launch | a *personal* developer account must first run a closed test with **12+ testers for 14 days** ([rule](https://support.google.com/googleplay/android-developer/answer/14151465)); an *organisation* account is exempt |

Complete the Play Console steps in `mobile/PLAY_STORE.md` (data safety, privacy policy URL, test logins for review).

## 5. The beta (about a week)

Pick about **1 admin, 3 employees, 5 POCs, 3 vendors** across at least two regions. Give each their own login (section 2).
Ask each role to do their normal day:

- **Employee:** check in (with and without location), mark several dates at once, scan a few bottles IN/OUT *including once in airplane mode*, add a cash purchase with a bill photo, apply for leave.
- **POC:** confirm a delivery, flag one short, raise a ticket with photos, reply, upload a payment proof.
- **Vendor:** read orders / tickets / bills / bottles; confirm they cannot raise or reply.
- **Admin:** approve a leave, look at the Admin tab, press **Sync now**, reset a tester's password.

Watch while it runs: the API logs for lines containing `client error` (app crashes), `/api/v1/ready`, Google Play **Android vitals**
and **Pre-launch report**. Collect: anything confusing, anything slow on a weak connection, any number that differs between the web app and the phone (that would be a bug).

**Go / no-go for the wider launch:** no crashes in a week, every tester could finish their tasks unaided, and the 10:00 sync ran on every day
(`/sync/status` → `last_run_source: scheduled`, today's date).

## 6. Running it

- **Alerts:** vendors and POCs are told about ticket updates and due bills; employees and admins about leave requests and decisions, tickets assigned to them, and new tickets raised by a POC (the bell in the app). Push to phones needs Firebase (`mobile/README.md`); without it the alerts still appear inside the app.

- **Backups:** daily Postgres backups on, and **restore one into a scratch database once** before launch to prove it works.
- **A phone is lost / someone leaves:** web → Logins → **Set password** (all their phones are signed out). Employees: deactivate on the Team page.
- **A person asks to delete their data:** they use *Account → Request data deletion* (an email to your support address); remove the login on the web app and answer within the time in your privacy policy.
- **Roll back a bad release:** in Play Console halt the rollout and promote the previous build; the API is forward-compatible with the old app (new fields are added, none removed).
- **Updating the app:** bump `version` in `mobile/app.config.ts` (the build number goes up by itself), `npm run build:aab`, upload to *Internal testing* first, then a staged production rollout (20% → 100%).
