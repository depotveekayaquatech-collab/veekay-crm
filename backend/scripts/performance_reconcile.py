"""
Read-only: why did the performance report change between two moments?  Changes nothing (the whole run is one READ ONLY transaction).

    python scripts/performance_reconcile.py --partner blinkit --month 2026-10 --previous 2026-10-29T10:37+05:30 --current 2026-10-30T10:37+05:30
    python scripts/performance_reconcile.py --partner zepto --previous-snapshot <id> --current-snapshot <id> --employee <user id>
    python scripts/performance_reconcile.py --partner blinkit            # the last kept report (or yesterday) against right now

Each side is a kept report (--*-snapshot), a time rebuilt from the records (--previous / --current, with a time zone), or, for --current, right now.
For every employee it prints the earlier and later figure and splits the difference into named causes: a newly finished day, entries
added, entries removed (who, when, the history), stores that changed hands. What the records cannot explain is printed as UNEXPLAINED.
Run it inside the API container to read production:   fly ssh console -C "python scripts/performance_reconcile.py --partner blinkit"
"""
import argparse
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import performance_reconciliation_service as rec, performance_service as ps  # noqa: E402


def when(v) -> str:
    return v.astimezone(rec._tz()).strftime("%d %b %H:%M IST") if isinstance(v, datetime) else str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partner", required=True, help="platform slug, e.g. blinkit or zepto")
    ap.add_argument("--month", help="2026-10 (default: the month of yesterday)")
    ap.add_argument("--previous", help="ISO time with zone, e.g. 2026-10-29T10:37+05:30")
    ap.add_argument("--current", help="ISO time with zone (default: right now)")
    ap.add_argument("--previous-snapshot", type=uuid.UUID)
    ap.add_argument("--current-snapshot", type=uuid.UUID)
    ap.add_argument("--employee", type=uuid.UUID, help="only this user id")
    a = ap.parse_args()

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        org_id = db.execute(select(User.organization_id).limit(1)).scalar_one()
        partner = ps._partner(db, a.partner.strip().lower())
        month = ps.parse_month(a.month, ps.business_today())
        at = lambda v: None if not v else datetime.fromisoformat(v)          # noqa: E731
        for v in (a.previous, a.current):
            if v and at(v).tzinfo is None:
                ap.error("times need a time zone, e.g. 2026-10-29T10:37+05:30")
        curr = rec.point_for(db, org_id, partner, month, snapshot_id=a.current_snapshot, at=at(a.current))
        if a.previous or a.previous_snapshot:
            prev = rec.point_for(db, org_id, partner, month, snapshot_id=a.previous_snapshot, at=at(a.previous))
        else:
            earlier = [s for s in rec.list_snapshots(db, org_id, partner.slug, month) if s["generated_at"] < curr.state.cutoff]
            prev = (rec.point_for(db, org_id, partner, month, snapshot_id=earlier[0]["id"]) if earlier
                    else rec.point_for(db, org_id, partner, month, at=curr.state.cutoff - timedelta(days=1)))
        out = rec.compare(db, org_id, partner, month, prev, curr, a.employee)
    finally:
        db.rollback()
        db.close()

    s = out["summary"]
    print(f"{out['partner_label']} {out['month']}: {s['status_label']}  ({s['verified']} verified, {s['reconciled']} reconciled, {s['requires_review']} need review, "
          f"{s['unverifiable']} unverifiable; {s['unexplained_total']} store-days unexplained)")
    for label, side in (("earlier", out["previous"]), ("later  ", out["current"])):
        print(f"  {label}: {when(side['at'])} - {side['source']}; {side['judged_days']} days counted (holidays are not special); stores: {side['scope_basis']}")
    for note in out["notes"]:
        print(f"  NOTE: {note}")
    print()
    for r in out["employees"]:
        e, u = r["explained"], r["unexplained"]
        print(f"{r['employee_name']:<14} {r['previous']['done']:>6,}/{r['previous']['expected']:<6,} -> {r['current']['done']:>6,}/{r['current']['expected']:<6,}  "
              f"{r['delta']:+,}  [{r['status_label']}]")
        parts = [("newly finished day", e["new_days"]),
                 ("entries added", e["entries_added"]), ("entries removed", -e["entries_removed"]), ("stores gained", e["stores_gained"]),
                 ("stores lost", -e["stores_lost"])]
        print("    " + ", ".join(f"{k} {v:+,}" for k, v in parts if v) + (f", UNEXPLAINED {u['total']:,}" if u["total"] else ", nothing unexplained"))
        for x in r["records"]["removed"]:
            who = f"by {x['by']} ({x['by_role']})" if x["by"] else "NOBODY NAMED"
            print(f"    removed: entry {x['entry_id']} store {x['store_code']} {x['date']} {x['kind']} {who} at {when(x['at'])}; reason: {x['reason'] or 'none recorded'}")
        for x in r["records"]["removed_without_evidence"]:
            print(f"    UNEXPLAINED: store {x['store_code'] or x['store_id']} {x['date']} lost its entry with no record of how")
    return 1 if s["requires_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
