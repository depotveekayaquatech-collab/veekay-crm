"""
Copy compliance files from the local UPLOAD_DIR into the configured object storage.

    STORAGE_BACKEND=s3 S3_BUCKET=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... [S3_ENDPOINT_URL=...] \
        python scripts/migrate_storage.py [--delete-local] [--dry-run]

Safe to re-run: a file that already exists in the bucket is skipped. Local files are only
removed with --delete-local, and only after the copy is confirmed in the bucket.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.compliance_document import ComplianceDocument  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete-local", action="store_true", help="remove each local file after it is confirmed in the bucket")
    ap.add_argument("--dry-run", action="store_true", help="only report what would be copied")
    args = ap.parse_args()

    if settings.STORAGE_BACKEND.strip().lower() != "s3":
        print("Set STORAGE_BACKEND=s3 (and the S3_* settings) first — that is where the files are copied to.")
        return 2
    storage.healthcheck()

    local = storage.LocalBackend()
    db = SessionLocal()
    copied = skipped = missing = 0
    try:
        for key, in db.execute(select(ComplianceDocument.file_key)):
            if storage.exists(key):
                skipped += 1
                continue
            if not local.exists(key):
                missing += 1
                print(f"  missing locally and in the bucket: {key}")
                continue
            if args.dry_run:
                copied += 1
                continue
            storage.save(key, local.read(key))
            if not storage.exists(key):
                print(f"  COPY NOT CONFIRMED, left alone: {key}")
                continue
            copied += 1
            if args.delete_local:
                local.delete(key)
    finally:
        db.close()
    print(f"{'Would copy' if args.dry_run else 'Copied'} {copied}, already in the bucket {skipped}, missing everywhere {missing}.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
