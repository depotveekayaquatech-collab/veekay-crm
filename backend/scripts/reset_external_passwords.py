"""
Give vendor / POC logins their own random passwords (run this before real people use the mobile app).

    python scripts/reset_external_passwords.py --dry-run                        # how many accounts would change
    python scripts/reset_external_passwords.py --only-default --out passwords.csv   # every account still on the standard password
    python scripts/reset_external_passwords.py --emails a@supplier.com,b@blinkit.com --out beta.csv   # just these (a beta group)
    python scripts/reset_external_passwords.py --emails-file beta.txt --out beta.csv

Writes a CSV of `login,password,name,phone,kind` for you to hand out (WhatsApp / SMS). Keep that file private and delete
it after sending: passwords are stored only as hashes, so it is the one place they exist. Each changed account is signed
out of every phone, unlocked, and recorded in the audit log. Accounts you don't select are left alone.
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402

from app.core.security import generate_temp_password, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.external_account import ExternalAccount, ExternalSession  # noqa: E402
from app.models.organization import Organization  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only-default", action="store_true", help="every account that still has the standard starting password")
    ap.add_argument("--emails", help="comma-separated logins")
    ap.add_argument("--emails-file", help="a text file with one login per line")
    ap.add_argument("--out", default="new-passwords.csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    wanted: set[str] = set()
    if a.emails:
        wanted |= {e.strip().lower() for e in a.emails.split(",") if e.strip()}
    if a.emails_file:
        wanted |= {line.strip().lower() for line in Path(a.emails_file).read_text(encoding="utf-8").splitlines() if line.strip()}
    if not (a.only_default or wanted):
        ap.error("choose who: --only-default, --emails or --emails-file")

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug="veekay").one()
        q = select(ExternalAccount).where(ExternalAccount.organization_id == org.id, ExternalAccount.is_active.is_(True))
        rows = [r for r in db.execute(q.order_by(ExternalAccount.kind, ExternalAccount.email)).scalars()
                if (a.only_default and r.must_change_password) or r.email in wanted]
        missing = wanted - {r.email for r in rows}
        print(f"{len(rows)} account(s) selected" + (f"; not found / inactive: {sorted(missing)}" if missing else ""))
        if a.dry_run or not rows:
            print("Dry run: nothing was written." if a.dry_run else "Nothing to do.")
            return

        now = datetime.now(timezone.utc)
        with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["login", "password", "name", "phone", "kind"])
            for r in rows:
                pw = generate_temp_password()
                r.password_hash = hash_password(pw)
                r.must_change_password = False
                r.failed_login_attempts = 0
                r.locked_until = None
                db.execute(update(ExternalSession).where(ExternalSession.account_id == r.id, ExternalSession.revoked_at.is_(None)).values(revoked_at=now))
                db.add(AuditLog(user_id=None, organization_id=org.id, action="external_account.password_reset", entity_type="external_account",
                                entity_id=str(r.id), metadata_json={"login": r.email, "generated": True, "via": "script"}))
                w.writerow([r.email, pw, r.full_name, r.phone or "", r.kind])
        db.commit()
        print(f"Done. {len(rows)} new passwords written to {a.out}. Hand them out, then delete that file.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
