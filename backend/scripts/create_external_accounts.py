"""
Create the vendor and POC logins in the standard format, ahead of the app they will use.

    python scripts/create_external_accounts.py --dry-run     # show what would be created, change nothing
    python scripts/create_external_accounts.py               # create / refresh (Blinkit stores)
    python scripts/create_external_accounts.py --platform all

    vendor   <name>@supplier.com    password 123456
    POC      <name>@blinkit.com     password <name>@123

Safe to re-run: new people are added, existing accounts keep their password, and each account's store list is refreshed
from the stores sheet. These are NOT CRM users (they have no role and can't sign in to the CRM); see
app/models/external_account.py. Every account is flagged must_change_password.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.services import external_account_service as svc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", default="blinkit", help="blinkit (default), zepto, or all")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    platforms = None if a.platform == "all" else {a.platform.lower()}

    db = SessionLocal()
    try:
        vendors, pocs = svc.build_plan(db, platforms)
        svc.check_unique([vendors, pocs])
        for label, plan in (("Vendors", vendors), ("POCs", pocs)):
            print(f"{label}: {len(plan.people)} accounts · skipped placeholders: {len(plan.skipped)}"
                  f" · names shared by several people (split by phone): {len(plan.split_names)}")
            for p in plan.people[:3]:
                print(f"   e.g. {p.email}  /  {p.password}   ({p.name}, {len(p.store_ids)} store(s))")
        if a.dry_run:
            print("Dry run: nothing was written.")
            return
        org = db.query(Organization).filter_by(slug="veekay").one()
        print(svc.apply(db, org.id, [vendors, pocs]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
