# Backup and restore

What cannot be rebuilt from the code, and where its copy lives.

| What | Where it lives | Backup |
|---|---|---|
| Database (staff, stores, entries, payroll, vendor payments, audit trail) | Postgres (Neon) | Provider restore window **plus** a nightly encrypted dump in a second bucket (`db/`) |
| Uploaded files (cards, invoices, payment proofs, photos) | Tigris bucket, the key is stored in the database | Daily copy into the second bucket (`files/`); nothing is ever deleted from the copy |
| Code | GitHub | Already copied on every laptop that cloned it |
| Fly secrets (`fly secrets list` shows names only) | Fly | **Not backed up.** Keep the values in a password manager. |
| Android signing key / Firebase project | EAS, Firebase console | Not covered here; make sure the account owner can recover both |

A database copy alone is not enough: the database holds file *keys*, the bucket holds the bytes. Both are copied by the same workflow
([.github/workflows/backup.yml](../.github/workflows/backup.yml)), a few minutes apart.

## One-time setup (needs you: accounts, keys, a bit of cost)

1. **Make a second bucket in a different place from the live one.** A backup in the same account dies with the account.
   Cheapest sensible choices: Backblaze B2, Cloudflare R2 or a Tigris bucket under a separate login. Keep it private. Create a key scoped to that bucket only.
2. **A read-only database login** for the dump. In the Neon console create a role that can read the tables (Neon: Roles, then grant `pg_read_all_data`), and copy its connection string.
   Use the plain form `postgresql://USER:PASS@HOST/DB?sslmode=require` (no `+psycopg`). Prefer the direct (non-pooled) host.
3. **A passphrase** for the dumps, 20+ random characters. Put it in your password manager *and* give it to one other trusted person.
   Without it the dumps cannot be opened, and nobody, including us, can recover it.
4. **A read-only key for the live file bucket** (Tigris console, access keys). The write key the API uses is not needed here.
5. Add these as repository secrets (GitHub, Settings, Secrets and variables, Actions):

   | Secret | Value |
   |---|---|
   | `PROD_DATABASE_URL` | step 2 |
   | `BACKUP_PASSPHRASE` | step 3 |
   | `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | step 1 |
   | `FILES_S3_ENDPOINT`, `FILES_S3_BUCKET`, `FILES_S3_ACCESS_KEY_ID`, `FILES_S3_SECRET_ACCESS_KEY` | step 4 (endpoint `https://fly.storage.tigris.dev`; bucket name is the one in the Fly secret `S3_BUCKET`) |

6. GitHub, Actions, **Backup**, Run workflow. All of `db-backup`, `files-mirror` and `restore-test` should go green. Open the restore-test summary and compare the row counts with the app.
7. Optional: set a lifecycle rule on the backup bucket to expire `db/` after 400 days. The workflow already deletes daily dumps older than 35 days and keeps the one from the 1st of each month.

Repository admins get an email when a scheduled run fails. GitHub switches scheduled workflows off after 60 days without any repository activity; this repository is pushed to far more often than that, but if work ever stops, run the workflow by hand.

## Also do in the Neon console (a minute, no code)

Open the project, **Backup & Restore**, and write down the restore window your plan gives. Test **Restore to a point in time** into a *branch* once, open it, then delete the branch. This is the fast path for "someone deleted something this morning". The nightly dump is the slow path for "the provider account is gone".

## Restore the database from a dump

You need the passphrase and read access to the backup bucket. Use a PostgreSQL client of version 17 or newer.

```sh
# 1. pick and download the dump (names look like veekay-20261104-2030.dump.gpg)
rclone lsf :s3,provider=Other,endpoint=ENDPOINT,access_key_id=KEY,secret_access_key=SECRET:BUCKET/db | sort | tail
rclone copyto :s3,...:BUCKET/db/veekay-YYYYMMDD-HHMM.dump.gpg dump.gpg

# 2. decrypt (asks for the passphrase)
gpg --output dump.dump --decrypt dump.gpg

# 3. restore into an EMPTY database (a new Neon project/branch, or local Postgres)
createdb veekay_restored
pg_restore --no-owner --no-privileges -d veekay_restored dump.dump
```

Then point the API at it: `fly secrets set DATABASE_URL="postgresql+psycopg://..."`. The release command runs `alembic upgrade head`, so a dump taken before the latest migration is brought forward automatically.
Run `backend/scripts/storage_audit.py` against the restored database and confirm `referenced but missing: 0`.

Never restore over the live database to "try it out". Restore into a new, empty one and switch only when it checks out.

## Restore files

```sh
# copy the whole backup (or just one prefix) back into the live bucket; never use "sync" in this direction
rclone copy BACKUP:bucket/files LIVE:bucket
```

## Checking it keeps working

- Every Sunday the workflow restores the newest dump into a scratch Postgres and writes row counts to the run summary. Glance at it monthly; a restore that was never tried is not a backup.
- Once a quarter, do the full restore above into a throwaway database and open a few documents.
- Write down the date, the dump name and who checked.

## What this does not protect against

- Someone with the Fly or GitHub owner login deleting everything. Keep the owner accounts to two people, with two-factor sign-in.
- Data lost between nightly dumps (up to 24 hours). The Neon point-in-time window covers that gap, within whatever your plan allows.
- A leaked passphrase together with a leaked bucket key. Keep them in different places.
