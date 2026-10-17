"""
READ-ONLY storage audit: do the files the database points to really exist, and what is in the bucket that nothing points to?

    python scripts/storage_audit.py [--grace-days 14] [--json report.json] [--list-limit 25]

On the production machine:   fly ssh console -C "python scripts/storage_audit.py"      (from backend/)

It NEVER deletes, moves, rewrites or uploads anything, and it never prints a signed link or a secret. It lists the bucket
once (1 Tigris "Class A" request per 1,000 objects) instead of checking every file separately.

Reports
  * references per table, and which storage_backend value each row records (local / s3);
  * REFERENCED BUT MISSING: the database points at a key that is not in storage (a broken attachment);
  * SIZE MISMATCH: the stored object is not the size the database recorded (possible overwrite or corruption);
  * UNREFERENCED: an object nothing points to. Only objects older than --grace-days are listed as orphan candidates,
    because a fresh upload may be in flight. They are NEVER removed here; a human decides after reading this report;
  * total storage used, by top-level folder.
Exit code 0 = clean, 1 = missing or mismatched files found, 2 = could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.cash_purchase import CashPurchase  # noqa: E402
from app.models.compliance_document import ComplianceDocument, ComplianceDocumentVersion  # noqa: E402
from app.models.external_activity import TicketAttachment  # noqa: E402
from app.models.test_report import TestReport  # noqa: E402
from app.services import storage_monitor  # noqa: E402


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:,.1f} MB"


def references(db) -> list[dict]:
    """Every (table, id, key, recorded size, recorded backend) the database holds."""
    rows: list[dict] = []
    for table, model, key, size, backend in (
        ("compliance_documents", ComplianceDocument, "file_key", "size_bytes", "storage_backend"),
        ("compliance_document_versions", ComplianceDocumentVersion, "file_key", "size_bytes", "storage_backend"),
        ("test_reports", TestReport, "file_key", "size_bytes", "storage_backend"),
        ("ticket_attachments", TicketAttachment, "file_key", "size_bytes", None),
        ("cash_purchases", CashPurchase, "proof_key", "proof_size_bytes", None),
    ):
        cols = [model.id, getattr(model, key), getattr(model, size)] + ([getattr(model, backend)] if backend else [])
        for r in db.execute(select(*cols)):
            if r[1]:
                rows.append({"table": table, "id": str(r[0]), "key": r[1], "size": r[2], "backend": r[3] if backend else None})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only storage audit")
    ap.add_argument("--grace-days", type=int, default=14, help="an unreferenced object younger than this is not reported as an orphan")
    ap.add_argument("--json", help="also write the full report to this file")
    ap.add_argument("--list-limit", type=int, default=25, help="how many problem keys to print per section")
    args = ap.parse_args()

    backend_name = settings.STORAGE_BACKEND.strip().lower()
    try:
        storage.healthcheck()
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot reach the '{backend_name}' storage: {type(exc).__name__}. Nothing was checked.")
        return 2

    db = SessionLocal()
    try:
        refs = references(db)
    finally:
        db.close()

    inventory = {k: (size, modified) for k, size, modified in storage.list_objects()}
    referenced = {r["key"] for r in refs}

    by_table = Counter(r["table"] for r in refs)
    backends = Counter((r["table"], r["backend"]) for r in refs if r["backend"])
    missing = [r for r in refs if r["key"] not in inventory]
    mismatched = [r for r in refs if r["key"] in inventory and r["size"] is not None and inventory[r["key"]][0] != r["size"]]
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.grace_days)
    unreferenced = [(k, s, m) for k, (s, m) in inventory.items() if k not in referenced]
    orphan_candidates = [(k, s, m) for k, s, m in unreferenced if m < cutoff]
    total = sum(s for s, _ in inventory.values())
    folders: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for k, (s, _) in inventory.items():
        f = k.split("/", 1)[0]
        folders[f][0] += 1
        folders[f][1] += s
    not_on_current = [r for r in refs if r["backend"] and r["backend"] != backend_name]

    print(f"Storage backend now: {backend_name}   (bucket {'set' if settings.S3_BUCKET else 'not set'})")
    print(f"Objects in storage: {len(inventory):,}   total {_mb(total)}")
    print("\nReferences in the database:")
    for t, n in by_table.most_common():
        print(f"  {t:32} {n:>7,}")
    print("\nRecorded storage_backend per table (rows whose files were saved on that backend):")
    for (t, b), n in sorted(backends.items()):
        print(f"  {t:32} {b:8} {n:>7,}")
    if not_on_current:
        print(f"  NOTE {len(not_on_current):,} rows say they were saved on a different backend than the current one: "
              "check they are present below (they are only fine if the files were copied).")

    def section(title: str, items, fmt):
        print(f"\n{title}: {len(items):,}")
        for it in items[: args.list_limit]:
            print("  " + fmt(it))
        if len(items) > args.list_limit:
            print(f"  ... and {len(items) - args.list_limit:,} more (use --json for the full list)")

    section("REFERENCED BUT MISSING (broken attachments)", missing, lambda r: f"{r['table']} {r['id']}  {r['key']}")
    section("SIZE MISMATCH (object is not the recorded size)", mismatched,
            lambda r: f"{r['table']} {r['id']}  recorded {r['size']:,} B, stored {inventory[r['key']][0]:,} B  {r['key']}")
    print(f"\nUNREFERENCED objects: {len(unreferenced):,}  ({_mb(sum(s for _, s, _ in unreferenced))}); "
          f"older than {args.grace_days} days (orphan candidates, NOT deleted): {len(orphan_candidates):,}  "
          f"({_mb(sum(s for _, s, _ in orphan_candidates))})")
    for k, s, m in orphan_candidates[: args.list_limit]:
        print(f"  {m:%Y-%m-%d}  {s:>10,} B  {k}")
    usage = storage_monitor.summarize((k, s, m) for k, (s, m) in inventory.items())
    print(f"\nQuota watch: {usage['used_percent']}% of the configured {settings.STORAGE_QUOTA_GB:g} GB warning level "
          f"(warn at {settings.STORAGE_WARN_PERCENT}%); added in the last 7 days {_mb(usage['last_7_days_bytes'])} "
          f"(previous weekly average {_mb(usage['previous_weekly_average_bytes'])}).")
    if usage["over_quota"] or usage["near_quota"]:
        print("  WARNING: storage is at or near the configured quota (paid storage starts after the provider's free allowance).")
    if usage["unusual_growth"]:
        print("  WARNING: storage grew unusually fast this week.")
    print("\nStorage by top-level folder:")
    for f, (n, s) in sorted(folders.items(), key=lambda x: -x[1][1]):
        print(f"  {f:34} {n:>7,} files  {_mb(s):>12}")
    print("\nThis report changed nothing. Orphan candidates must be reviewed by a person before anything is removed.")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "backend": backend_name, "objects": len(inventory), "total_bytes": total,
            "references": dict(by_table), "missing": missing, "size_mismatch": mismatched,
            "orphan_candidates": [{"key": k, "size": s, "modified": m.isoformat()} for k, s, m in orphan_candidates],
        }, indent=2), encoding="utf-8")
    return 1 if (missing or mismatched) else 0


if __name__ == "__main__":
    raise SystemExit(main())
