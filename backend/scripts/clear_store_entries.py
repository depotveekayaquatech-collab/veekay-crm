"""
Remove the entries of one store (a store that should never have had any), the audited way: every row is deleted through the same path the CRM's
"clear" button uses, so the history keeps a CLEARED event naming the actor and the reason, and the database keeps a copy of each deleted row.

    python scripts/clear_store_entries.py --list-non-live                          # read-only: stores that are not live but hold entries
    python scripts/clear_store_entries.py --platform zepto --store Baprola         # DRY RUN: which store matched and how many entries it holds
    python scripts/clear_store_entries.py --platform zepto --store Baprola --actor ADMIN001 --apply

Nothing is deleted without --apply. A name that matches several stores is refused (narrow it, or pass --code with the Outlet ID).
A LIVE store is refused unless --even-if-live is given: a live store's entries are normally real.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core import audit_context  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.order_entry import OrderEntry  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.store import Store, StoreStatus  # noqa: E402
from app.models.user import User  # noqa: E402


def list_non_live(db) -> None:
    rows = db.execute(
        select(Store.name, Store.external_code, Store.status, Organization.name, func.count(OrderEntry.id), func.min(OrderEntry.order_date), func.max(OrderEntry.order_date))
        .join(OrderEntry, OrderEntry.store_id == Store.id).join(Organization, Organization.id == Store.partner_organization_id)
        .where(Store.status != StoreStatus.LIVE.value).group_by(Store.id, Organization.name).order_by(Store.status, Store.name)
    ).all()
    print(f"{len(rows)} store(s) that are not live still hold entries:")
    for name, code, st, platform, n, first, last in rows:
        print(f"  {platform:8} {st:8} {name} ({code}): {n} entries, {first} to {last}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-non-live", action="store_true")
    ap.add_argument("--platform", help="platform slug, e.g. zepto")
    ap.add_argument("--store", help="part of the store's name")
    ap.add_argument("--code", help="the store's Outlet ID (to pick one of several)")
    ap.add_argument("--actor", help="employee code of the admin the deletion is recorded under (required with --apply)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--even-if-live", action="store_true")
    a = ap.parse_args()

    with SessionLocal() as db:
        if a.list_non_live:
            return list_non_live(db)
        if not (a.platform and (a.store or a.code)):
            raise SystemExit("Give --platform and --store (or --code), or use --list-non-live.")
        q = select(Store).join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == a.platform.lower())
        if a.store:
            q = q.where(Store.name.ilike(f"%{a.store}%"))
        if a.code:
            q = q.where(Store.external_code == a.code)
        stores = list(db.execute(q).scalars())
        if not stores:
            raise SystemExit("No store matched.")
        if len(stores) > 1:
            for s in stores:
                print(f"  {s.name} ({s.external_code}) {s.status}")
            raise SystemExit("More than one store matched: narrow --store or add --code.")
        store = stores[0]
        entries = list(db.execute(select(OrderEntry).where(OrderEntry.store_id == store.id).order_by(OrderEntry.order_date)).scalars())
        print(f"{store.name} ({store.external_code}), {store.status}: {len(entries)} entries" + (f", {entries[0].order_date} to {entries[-1].order_date}" if entries else ""))
        if store.status == StoreStatus.LIVE.value and not a.even_if_live:
            raise SystemExit("This store is LIVE. Pass --even-if-live if you really mean to clear its entries.")
        if not a.apply:
            return print("Dry run: nothing deleted. Add --apply --actor <ADMIN CODE> to delete.")
        if not a.actor:
            raise SystemExit("--actor is required with --apply.")
        actor = db.execute(select(User).where(User.employee_code == a.actor, User.organization_id == store.organization_id)).scalar_one_or_none()
        if actor is None:
            raise SystemExit(f"No account '{a.actor}'.")
        audit_context.bind(db, actor, reason="Cleared: this store is not supposed to have entries (clear_store_entries.py)", source="script")
        for e in entries:
            db.delete(e)
        db.commit()
        print(f"Deleted {len(entries)} entries of {store.name}. Each is in the history as CLEARED, and a copy is kept in deleted_rows.")


if __name__ == "__main__":
    main()
