"""
Demo data for the Vendor Payments tab: 10 dummy vendors (codes V9001 to V9010, so they can never clash with real ones) and three months of
bills and payments ending with the current month, pushed through the same sync routine the real feed uses.

    python scripts/seed_busy_demo.py            add / refresh the demo data (safe to re-run: nothing is duplicated)
    python scripts/seed_busy_demo.py --remove   delete the demo vendors and everything under them

Includes: V9001 with an opening balance (owed since the first month), and V9002 whose payments exceed its bills in the middle month.
Refuses to run when ENVIRONMENT=production unless --force is given.
"""
import argparse
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.busy_ledger import BusyLedgerEntry, BusyUnmatchedEntry, BusyVendor, BusyVendorAlias
from app.services.busy_ledger_service import current_month, parse_month
from app.services.busy_sync_service import run_sync

DEMO_VENDORS = [
    ("V9001", "Sharma Traders", "Gurugram", "25000.00"),
    ("V9002", "Gupta Packaging", "Noida", "0"),
    ("V9003", "Aqua Caps & Closures", "Pune", "0"),
    ("V9004", "Bharat Plastics", "Mumbai", "0"),
    ("V9005", "Southern Labels", "Bengaluru", "0"),
    ("V9006", "Kaveri Transport", "Chennai", "0"),
    ("V9007", "Delhi Chemicals", "New Delhi", "0"),
    ("V9008", "Himalayan Crates", "Dehradun", "0"),
    ("V9009", "Royal Print House", "Jaipur", "0"),
    ("V9010", "Metro Spares", "Hyderabad", "0"),
]
DEMO_CODES = [code for code, *_ in DEMO_VENDORS]


def first_months(count: int = 3) -> list[date]:
    month = parse_month(current_month())
    out = [month]
    for _ in range(count - 1):
        month = date(month.year - (month.month == 1), 12 if month.month == 1 else month.month - 1, 1)
        out.insert(0, month)
    return out


def demo_entries(months: list[date]) -> list[dict]:
    rng = random.Random(9001)
    rows: list[dict] = []
    for code, name, city, _ in DEMO_VENDORS:
        for m_index, month in enumerate(months):
            bills = rng.choice((1, 2, 3))
            for n in range(bills):
                rows.append({"vendor_code": code, "account_name": f"{name} {city} {code}", "date": month.replace(day=rng.randint(2, 12)).isoformat(), "type": "BILL",
                             "amount": f"{rng.randint(20, 200) * 1000 + rng.choice((0, 500, 250)):.2f}", "voucher_no": f"PUR/{month:%y%m}/{code[-2:]}{n}",
                             "narration": f"Supply {month:%b %Y} lot {n + 1}"})
            if code == "V9002" and m_index == 1:           # a month where payments exceed bills
                rows.append({"vendor_code": code, "date": month.replace(day=20).isoformat(), "type": "PAYMENT", "amount": "400000.00",
                             "voucher_no": f"PAY/{month:%y%m}/{code[-2:]}X", "narration": "Settled earlier dues in one go"})
            else:
                for n in range(rng.choice((0, 1, 2))):
                    rows.append({"vendor_code": code, "date": month.replace(day=rng.randint(14, 27)).isoformat(), "type": "PAYMENT",
                                 "amount": f"{rng.randint(10, 120) * 1000:.2f}", "voucher_no": f"PAY/{month:%y%m}/{code[-2:]}{n}", "narration": "Bank transfer"})
    return rows


def add(db) -> None:
    months = first_months()
    for code, name, city, opening in DEMO_VENDORS:
        vendor = db.query(BusyVendor).filter_by(vendor_code=code).one_or_none()
        if vendor is None:
            db.add(BusyVendor(vendor_code=code, name=name, city=city, opening_balance=Decimal(opening), opening_date=months[0] if Decimal(opening) else None))
    db.commit()
    out = run_sync(db, entries=demo_entries(months), source="API", triggered_by="seed_busy_demo.py")
    print(f"Demo vendors ready. Entries: {out.inserted} added, {out.updated} updated, {out.unchanged} unchanged, {out.rejected} rejected.")


def remove(db) -> None:
    db.execute(delete(BusyUnmatchedEntry).where(BusyUnmatchedEntry.vendor_code.in_(DEMO_CODES)))
    db.execute(delete(BusyLedgerEntry).where(BusyLedgerEntry.vendor_code.in_(DEMO_CODES)))
    db.execute(delete(BusyVendorAlias).where(BusyVendorAlias.vendor_code.in_(DEMO_CODES)))
    deleted = db.execute(delete(BusyVendor).where(BusyVendor.vendor_code.in_(DEMO_CODES))).rowcount
    db.commit()
    print(f"Removed {deleted} demo vendors and their entries.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="delete the demo vendors and their entries")
    parser.add_argument("--force", action="store_true", help="allow running when ENVIRONMENT=production")
    args = parser.parse_args()
    if settings.ENVIRONMENT.strip().lower() == "production" and not args.force:
        sys.exit("Refusing to write demo data in production (use --force if you really mean it).")
    db = SessionLocal()
    try:
        (remove if args.remove else add)(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
