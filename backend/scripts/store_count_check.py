"""
Read-only check: do the CRM's store numbers match the store sheet?  Changes nothing.

    python scripts/store_count_check.py                 # CRM numbers, plus a sheet comparison when STORE_SYNC_SHEETS is set
    python scripts/store_count_check.py --names 40      # list up to 40 store names per mismatch (default 15)

Per platform it prints:
  * the CRM's stores by status (Live / Pending / Close) and how many names or Outlet IDs are repeated,
  * the last few store imports (rows read, stores added, updated) from the audit log,
  * when a sheet is configured: the sheet's rows by status (read with the same rules as the import), rows the import cannot use
    (no name / no ID), repeated names, and which sheet stores are missing from the CRM or sit in the CRM under another status.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.organization import Organization, OrganizationKind  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.services import store_sync_service as sync  # noqa: E402
from app.services.store_service import name_key  # noqa: E402


def _sample(items, n):
    items = sorted(items)
    return ", ".join(items[:n]) + (f"  … (+{len(items) - n} more)" if len(items) > n else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", type=int, default=15, help="how many names to list per mismatch")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        partners = db.execute(select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value).order_by(Organization.name)).scalars().all()
        sources = settings.sheet_sources()
        for partner in partners:
            stores = db.execute(select(Store).where(Store.partner_organization_id == partner.id)).scalars().all()
            by_status = Counter(s.status for s in stores)
            print(f"\n=== {partner.name} ({partner.slug}) ===")
            print(f"CRM: {len(stores)} stores   Live {by_status.get('LIVE', 0)} · Pending {by_status.get('PENDING', 0)} · Close {by_status.get('CLOSE', 0)}")
            names = Counter(name_key(s.name) for s in stores)
            codes = Counter(s.external_code.strip().lower() for s in stores)
            print(f"     repeated names: {sum(1 for n in names.values() if n > 1)} · repeated Outlet IDs: {sum(1 for n in codes.values() if n > 1)}")

            runs = db.execute(
                select(AuditLog).where(AuditLog.action == "store.synced", AuditLog.entity_id == str(partner.id)).order_by(AuditLog.created_at.desc()).limit(4)
            ).scalars().all()
            for r in runs:
                m = r.metadata_json or {}
                print(f"     import {r.created_at:%Y-%m-%d %H:%M}: read {m.get('rows_read')} rows · added {m.get('created')} · updated {m.get('updated')} · {m.get('source')}")

            if partner.slug not in sources:
                print("Sheet: not configured on the server (STORE_SYNC_SHEETS), so the sheet side cannot be read from here.")
                continue
            sheet_id, gid = sources[partner.slug]
            try:
                rows = sync._fetch_rows(sheet_id, gid)
            except Exception as exc:  # noqa: BLE001
                print(f"Sheet: could not be read ({exc}).")
                continue
            cols = sync._resolve_columns(rows[0]) if rows else {}
            if "external_code" not in cols or "name" not in cols:
                print("Sheet: no 'Outlet ID' / 'Outlet Name' columns found.")
                continue
            st_col = cols.get("status")
            unusable, sheet = 0, {}
            status_count, unknown = Counter(), 0
            for r in rows:
                code, name = sync._clean(r.get(cols["external_code"])), sync._clean(r.get(cols["name"]))
                if not code or not name:
                    unusable += 1
                    continue
                raw = r.get(st_col) if st_col else None
                st = sync.parse_status(raw)
                if st is None:
                    unknown += 1
                status_count[st or "UNKNOWN"] += 1
                sheet.setdefault(name_key(name), []).append((name, code, st))
            print(f"Sheet: {len(rows)} rows   Live {status_count.get('LIVE', 0)} · Pending {status_count.get('PENDING', 0)} · Close {status_count.get('CLOSE', 0)} · "
                  f"unreadable status {unknown} (these become Pending when new)")
            print(f"       rows without a name or Outlet ID (never imported): {unusable}")
            twins = {k: v for k, v in sheet.items() if len(v) > 1}
            print(f"       store names that appear more than once in the sheet: {len(twins)} (only the first row of each is imported)")
            if twins:
                print("         e.g. " + _sample([v[0][0] for v in twins.values()], a.names))

            crm = {}
            for s in stores:
                crm.setdefault(name_key(s.name), []).append(s)
            missing = [v[0][0] for k, v in sheet.items() if k not in crm]
            print(f"       sheet stores whose NAME is not in the CRM: {len(missing)}")
            if missing:
                print("         " + _sample(missing, a.names))
            wrong = [(v[0][0], v[0][2], crm[k][0].status) for k, v in sheet.items() if k in crm and v[0][2] and v[0][2] != crm[k][0].status]
            print(f"       same name, different status (sheet vs CRM): {len(wrong)}")
            for n, s_sheet, s_crm in sorted(wrong)[: a.names]:
                print(f"         {n}: sheet {s_sheet}, CRM {s_crm}")
            extra = [s.name for k, g in crm.items() if k not in sheet for s in g]
            print(f"       CRM stores that are not in the sheet by name: {len(extra)}")
            if extra:
                print("         " + _sample(extra, a.names))
    finally:
        db.close()


if __name__ == "__main__":
    main()
