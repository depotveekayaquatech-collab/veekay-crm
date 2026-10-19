"""
Sync Cash Purchase (developer only).

    Store purchases (what employees recorded)  --sync-->  developer working copy (cash_sync_records)
        --review / edit / preview / confirm-->  order sheet (+ the cash_adjustments history)

Rules enforced here:
  * Sync only copies data into the working area. It never touches the order sheet.
  * One working row per source purchase (unique purchase_id): syncing again cannot add a purchase twice.
  * A purchase that changed at the source after it was synced is flagged CHANGED and waits for the developer.
  * Applying adds to the employee's existing entry (several purchases for one store + date are summed) and is
    refused for anything already applied, under row locks.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cash_adjustment import CashAdjustment, CashSyncRecord, CashSyncRun, SyncStatus
from app.models.cash_purchase import CashPurchase, PurchaseKind
from app.models.order_entry import OrderEntry
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.schemas.cash_sync import (
    RecordEdit,
    SourceSnapshot,
    StandardRate,
    StandardRateResult,
    SyncApplyFailure,
    SyncApplyResult,
    SyncOverview,
    SyncPreview,
    SyncPreviewPurchase,
    SyncPreviewRow,
    SyncRecordOut,
    SyncRunOut,
    SyncSummary,
    UploadResult,
)
from app.services import activity_service, store_sync_service
from app.services.cash_adjustment_service import apply_to_entry, calc_quantity
from app.services.cash_purchase_service import MAX_AMOUNT, _today
from app.services.order_service import _check_order_date

SOURCE_NAME = "Store Purchase Sheet"


def _err(code: int, message: str) -> HTTPException:
    return HTTPException(code, message)


def sync_code(run_id: uuid.UUID) -> str:
    return f"SYNC-{run_id.hex[:8].upper()}"


def purchase_code(purchase_id: uuid.UUID) -> str:
    return f"CP-{purchase_id.hex[:8].upper()}"


def _snapshot(p: CashPurchase) -> dict:
    from app.services.cash_purchase_service import _label

    return {
        "store_id": str(p.store_id) if p.store_id else None,
        "store_code": p.store.external_code if p.store else None,
        "store_name": p.store.name if p.store else None,
        "purchase_date": p.purchase_date.isoformat(),
        "amount": str(Decimal(p.amount).quantize(Decimal("0.01"))),
        "reason": _label(p.kind, p.category),
        "added_by": p.created_by.full_name if p.created_by else None,
    }


def _fingerprint(snap: dict) -> str:
    """Identity of what matters for the order sheet: which store, which day, how much."""
    raw = f"{snap.get('store_id')}|{snap.get('purchase_date')}|{snap.get('amount')}"
    return hashlib.sha256(raw.encode()).hexdigest()


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------

def _last_run(db: Session, user: User) -> CashSyncRun | None:
    return db.execute(
        select(CashSyncRun).where(CashSyncRun.organization_id == user.organization_id).order_by(CashSyncRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _pending_count(db: Session, user: User) -> int:
    return db.execute(
        select(func.count()).select_from(CashSyncRecord).where(
            CashSyncRecord.organization_id == user.organization_id, CashSyncRecord.status == SyncStatus.PENDING
        )
    ).scalar_one()


def _summary(db: Session, user: User, run: CashSyncRun) -> SyncSummary:
    return SyncSummary(
        sync_id=run.id, sync_code=sync_code(run.id), synced_at=run.created_at, records_found=run.records_found,
        new_records=run.new_count, changed_records=run.changed_count, already_processed=run.already_count,
        pending_review=_pending_count(db, user),
    )


def sync(db: Session, user: User) -> SyncSummary:
    """Bring the latest store purchases into the working area. Changes nothing on the order sheet."""
    purchases = db.execute(
        select(CashPurchase).where(
            CashPurchase.organization_id == user.organization_id, CashPurchase.kind == PurchaseKind.STORE.value
        ).order_by(CashPurchase.purchase_date, CashPurchase.created_at)
    ).scalars().unique().all()
    existing = {
        r.purchase_id: r
        for r in db.execute(select(CashSyncRecord).where(CashSyncRecord.organization_id == user.organization_id)).scalars()
    }
    run = CashSyncRun(
        organization_id=user.organization_id, created_by_user_id=user.id, created_by_name=user.full_name,
        records_found=len(purchases), new_count=0, changed_count=0, already_count=0,
    )
    db.add(run)
    db.flush()

    new = changed = already = 0
    for p in purchases:
        snap = _snapshot(p)
        rec = existing.get(p.id)
        if rec is None:
            db.add(CashSyncRecord(
                organization_id=user.organization_id, purchase_id=p.id, status=SyncStatus.PENDING,
                store_id=p.store_id, purchase_date=p.purchase_date, amount=p.amount,
                baseline=snap, current_source=snap, sync_id=run.id,
            ))
            new += 1
            continue
        rec.current_source = snap
        if _fingerprint(snap) != _fingerprint(rec.baseline):
            # The source moved on after the last sync: flag it for review, never act on it by itself.
            if rec.status != SyncStatus.CHANGED:
                rec.sync_id = run.id
            rec.status = SyncStatus.CHANGED
            changed += 1
        elif rec.status in (SyncStatus.APPLIED, SyncStatus.SKIPPED):
            already += 1
    run.new_count, run.changed_count, run.already_count = new, changed, already
    activity_service.record(
        db, actor=user, action="cash_sync.synced", entity_type="cash_sync", entity_id=run.id,
        metadata={"found": len(purchases), "new": new, "changed": changed, "already": already},
    )
    db.commit()
    db.refresh(run)
    return _summary(db, user, run)


# --------------------------------------------------------------------------
# upload a cash purchase sheet
# --------------------------------------------------------------------------

# Header -> field. Headers are matched case-insensitively; the downloaded "Cash Purchase Sheet" works as it is.
_UPLOAD_COLUMNS: dict[str, list[str]] = {
    "date": ["date", "purchase date", "purchase_date"],
    "code": ["store code", "outlet id", "outlet code", "store id", "code"],
    "name": ["store / place", "store name", "outlet name", "store", "place", "name"],
    "type": ["type"],
    "amount": ["amount (inr)", "amount (₹)", "amount", "cash purchase", "total amount"],
    "price": ["price per item", "price", "rate"],
    "reason": ["reason"],
    "added_by": ["added by"],
}
_SHEET_NAMESPACE = uuid.UUID("5b0a3f0e-7a52-4c1e-9d2b-3c1f6a8e4d17")


def _money(raw: str | None) -> Decimal | None:
    text = (raw or "").replace("₹", "").replace("INR", "").replace(",", "").strip()
    try:
        value = Decimal(text)
        if not value.is_finite():
            return None
        value = value.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return value if 0 < value <= MAX_AMOUNT else None


def _code_key(text: str | None) -> str:
    """A store code for comparing: case, spaces, dashes and other punctuation ignored; "8696.0" is 8696; leading zeros ignored."""
    t = (text or "").replace("\u00a0", " ").strip().lower()
    if re.fullmatch(r"\d+\.0+", t):
        t = t.split(".")[0]
    k = re.sub(r"[^a-z0-9]+", "", t)
    return (k.lstrip("0") or "0") if k.isdigit() else k


def _name_key(text: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


class _StoreIndex:
    """Every store of the organisation, looked up by code or by name the way a person would read them."""

    def __init__(self, stores: list[Store]):
        self.stores = stores
        self.by_code: dict[str, list[Store]] = {}
        self.by_name: dict[str, list[Store]] = {}
        for s in stores:
            self.by_code.setdefault(_code_key(s.external_code), []).append(s)
            self.by_name.setdefault(_name_key(s.name), []).append(s)
        self.named = [(_name_key(s.name), s) for s in stores]


def _resolve_store(index: _StoreIndex, code: str | None, name: str | None) -> Store | None:
    """The store a sheet row means, or None when it is unknown or ambiguous (the developer then picks it in review).

    The sheet's store id comes first (ignoring case, spaces, dashes, a trailing ".0" and leading zeros), then the name (ignoring
    punctuation), whichever column it was written in. After that: a store code written inside a longer label ("KS105 (8696)"),
    then a name that is the start of the store's name, or the other way round. Each step needs exactly one candidate, so a
    guess is never made between two stores."""
    values = [v for v in (code, name) if v and v.strip()]
    for v in values:                                              # 1) the id
        found = index.by_code.get(_code_key(v), [])
        if len(found) > 1:
            others = [_name_key(o) for o in values if o is not v]
            found = [s for s in found if _name_key(s.name) in others] or found
        if len(found) == 1:
            return found[0]
        if found:
            return None                                           # two stores share it and the name does not settle it
    for v in values:                                              # 2) the full name
        found = index.by_name.get(_name_key(v), [])
        if len(found) == 1:
            return found[0]
        if found:
            return None
    for v in values:                                              # 3) a store code inside a longer label
        tokens = {_code_key(t) for t in re.findall(r"[A-Za-z0-9]+", v)}
        found = [s for s in index.stores if len(_code_key(s.external_code)) >= 3 and _code_key(s.external_code) in tokens]
        if len(found) == 1:
            return found[0]
    for v in values:                                              # 4) the start of the name
        key = _name_key(v)
        if len(key) >= 6:
            found = [s for nk, s in index.named if len(nk) >= 6 and (nk.startswith(key) or key.startswith(nk))]
            if len(found) == 1:
                return found[0]
    return None


def _fix_store_columns(rows: list[dict], cols: dict[str, str | None], index: _StoreIndex) -> dict[str, str | None]:
    """When the sheet's store headings are not the usual words (or the named column holds something else), pick the column(s)
    whose values actually are this organisation's store ids / names."""
    sample = rows[:300]

    def rate(col: str) -> float:
        vals = [(r.get(col) or "").strip() for r in sample]
        vals = [v for v in vals if v]
        return sum(1 for v in vals if _resolve_store(index, v, None) is not None) / len(vals) if vals else 0.0

    taken = {cols[f] for f in ("date", "amount", "price", "type") if cols.get(f)}
    scores = {c: rate(c) for c in rows[0] if c not in taken}
    out = dict(cols)
    for field in ("code", "name"):
        have = out.get(field)
        if have and scores.get(have, 0) > 0:
            continue
        other = out.get("name" if field == "code" else "code")
        pool = {c: s for c, s in scores.items() if s > 0 and c != other}
        if pool:
            out[field] = max(pool, key=pool.get)
    return out


def upload_sheet(db: Session, user: User, filename: str, content: bytes) -> UploadResult:
    """Bring a cash purchase sheet (.xlsx / .csv, same columns as the downloaded sheet) into the review list.

    Like Sync, this only copies rows into the working area; the order sheet is untouched until the developer confirms.
    Safe to repeat: a row that is already in the app (same store + date + amount) or was uploaded before is skipped,
    so uploading the downloaded sheet back, or the same file twice, never adds a purchase twice."""
    rows = store_sync_service.rows_from_upload(filename, content)
    if not rows:
        raise store_sync_service.SyncError("The sheet has no data rows.")
    org = user.organization_id
    stores = db.execute(select(Store).where(Store.organization_id == org)).scalars().unique().all()
    index = _StoreIndex(stores)
    lower = {k.strip().lower(): k for k in rows[0]}
    cols = {f: next((lower[a] for a in aliases if a in lower), None) for f, aliases in _UPLOAD_COLUMNS.items()}
    cols = _fix_store_columns(rows, cols, index)
    if not cols["date"] or not cols["amount"] or not (cols["code"] or cols["name"]):
        raise store_sync_service.SyncError(
            "Could not find the columns. The sheet needs a Date column, an Amount column and a Store code (or Store name) column."
        )

    def cell(row: dict, field: str) -> str | None:
        return store_sync_service._clean(row.get(cols[field])) if cols[field] else None

    today = _today()
    in_app = {
        (sid, d, a): n for sid, d, a, n in db.execute(
            select(CashPurchase.store_id, CashPurchase.purchase_date, CashPurchase.amount, func.count())
            .where(CashPurchase.organization_id == org, CashPurchase.kind == PurchaseKind.STORE.value)
            .group_by(CashPurchase.store_id, CashPurchase.purchase_date, CashPurchase.amount)
        )
    }

    office = invalid = already_in_app = 0
    problems: list[str] = []
    seen: dict[tuple, int] = {}
    candidates: list[dict] = []
    for i, row in enumerate(rows, start=2):   # sheet row number (1 = header)
        raw_date = cell(row, "date")
        if (raw_date or "").lower() == "total":
            continue
        code, name = cell(row, "code"), cell(row, "name")
        kind = (cell(row, "type") or "").lower()
        if kind == "office" or (not code and (name or "").lower() == "office"):
            office += 1
            continue
        day = store_sync_service._parse_date(raw_date)
        amount = _money(cell(row, "amount"))
        why = (
            "the date can't be read" if day is None else "the date is in the future" if day > today
            else "the amount is missing or not a valid number" if amount is None
            else "there is no store" if not (code or name) else None
        )
        if why:
            invalid += 1
            if len(problems) < 5:
                problems.append(f"Row {i}: skipped, {why}.")
            continue
        store = _resolve_store(index, code, name)
        # Identity comes from what the sheet says, not from the store we matched, so a store added to the CRM later
        # (or a different pick made in review) never turns an old row into a "new" one on the next upload.
        key = (f"{(code or '').lower()}|{(name or '').lower() if not code else ''}", day, amount)
        n = seen[key] = seen.get(key, -1) + 1   # the 1st, 2nd... identical purchase of the day (two ₹100 buys are legitimate)
        if store and n < in_app.get((store.id, day, amount), 0):
            already_in_app += 1
            continue
        candidates.append({
            "pid": uuid.uuid5(_SHEET_NAMESPACE, f"{org}|{key[0]}|{day}|{amount}|{n}"), "store": store, "day": day,
            "amount": amount, "code": code, "name": name, "price": _money(cell(row, "price")),
            "reason": cell(row, "reason"), "added_by": cell(row, "added_by"),
        })

    known: set[uuid.UUID] = set()
    pids = [c["pid"] for c in candidates]
    for i in range(0, len(pids), 5000):
        known.update(db.execute(
            select(CashSyncRecord.purchase_id).where(CashSyncRecord.organization_id == org, CashSyncRecord.purchase_id.in_(pids[i:i + 5000]))
        ).scalars())
    fresh = [c for c in candidates if c["pid"] not in known]
    already_uploaded = len(candidates) - len(fresh)

    # Rows uploaded earlier that were left without a store: the sheet may match one now (better matching, or a store added since).
    rematched = 0
    by_pid = {c["pid"]: c for c in candidates if c["store"] is not None}
    if by_pid:
        for rec in db.execute(
            select(CashSyncRecord).where(
                CashSyncRecord.organization_id == org, CashSyncRecord.purchase_id.in_(list(by_pid)),
                CashSyncRecord.store_id.is_(None), CashSyncRecord.status == SyncStatus.PENDING,
            )
        ).scalars():
            s = by_pid[rec.purchase_id]["store"]
            rec.store_id = s.id
            for field in ("baseline", "current_source"):
                snap = dict(getattr(rec, field) or {})
                snap.update({"store_id": str(s.id), "store_code": s.external_code, "store_name": s.name})
                setattr(rec, field, snap)
            rematched += 1

    run = CashSyncRun(
        organization_id=org, created_by_user_id=user.id, created_by_name=user.full_name,
        records_found=len(candidates) + already_in_app, new_count=len(fresh), changed_count=0,
        already_count=already_uploaded + already_in_app,
    )
    db.add(run)
    db.flush()
    unmatched: dict[str, int] = {}
    for c in fresh:
        s = c["store"]
        snap = {
            "store_id": str(s.id) if s else None, "store_code": s.external_code if s else c["code"],
            "store_name": s.name if s else c["name"], "purchase_date": c["day"].isoformat(), "amount": str(c["amount"]),
            "reason": c["reason"] or "Uploaded sheet", "added_by": c["added_by"] or user.full_name,
        }
        if s is None:
            label = " ".join(x for x in (c["name"], f"({c['code']})" if c["code"] else None) if x)
            unmatched[label] = unmatched.get(label, 0) + 1
        db.add(CashSyncRecord(
            organization_id=org, purchase_id=c["pid"], status=SyncStatus.PENDING, store_id=s.id if s else None,
            purchase_date=c["day"], amount=c["amount"], price_per_item=c["price"], baseline=snap, current_source=snap, sync_id=run.id,
        ))
    if unmatched:
        shown = ", ".join(sorted(unmatched)[:8]) + (" …" if len(unmatched) > 8 else "")
        problems.append(f"{sum(unmatched.values())} row(s) have a store that could not be matched to one store in the CRM ({shown}). Pick the store in the review list.")
    if rematched:
        problems.append(f"{rematched} row(s) uploaded earlier without a store were matched this time.")
    if invalid > len(problems):
        problems.append(f"{invalid} row(s) in total were skipped as unreadable.")
    activity_service.record(
        db, actor=user, action="cash_sync.uploaded", entity_type="cash_sync", entity_id=run.id,
        metadata={"file": filename[:120], "rows": len(rows), "added": len(fresh), "already_in_app": already_in_app,
                  "already_uploaded": already_uploaded, "office": office, "invalid": invalid},
    )
    db.commit()
    db.refresh(run)
    return UploadResult(
        summary=_summary(db, user, run), rows_read=len(rows), added=len(fresh), already_in_app=already_in_app,
        already_uploaded=already_uploaded, unmatched_store=sum(unmatched.values()), office_rows=office, invalid_rows=invalid,
        rematched=rematched, warnings=problems[:12],
    )


def runs(db: Session, user: User) -> list[SyncRunOut]:
    rows = db.execute(
        select(CashSyncRun).where(CashSyncRun.organization_id == user.organization_id).order_by(CashSyncRun.created_at.desc()).limit(50)
    ).scalars().all()
    applied = dict(db.execute(
        select(CashSyncRecord.sync_id, func.count()).where(
            CashSyncRecord.organization_id == user.organization_id, CashSyncRecord.status == SyncStatus.APPLIED
        ).group_by(CashSyncRecord.sync_id)
    ).all())
    return [
        SyncRunOut(
            sync_id=r.id, sync_code=sync_code(r.id), synced_at=r.created_at, developer=r.created_by_name,
            records_found=r.records_found, new_records=r.new_count, changed_records=r.changed_count,
            already_processed=r.already_count, applied=applied.get(r.id, 0),
        )
        for r in rows
    ]


# --------------------------------------------------------------------------
# working data
# --------------------------------------------------------------------------

def _qtys(r: CashSyncRecord) -> tuple[int | None, int | None]:
    auto = calc_quantity(r.amount, r.price_per_item) if r.price_per_item else None
    final = r.final_qty_override if r.final_qty_override is not None else auto
    return auto, final


def _store_map(db: Session, user: User, ids: set) -> dict[uuid.UUID, Store]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(Store).where(Store.organization_id == user.organization_id, Store.id.in_(ids))).scalars().unique().all()
    return {s.id: s for s in rows}


def _out(r: CashSyncRecord, stores: dict[uuid.UUID, Store], run_codes: dict) -> SyncRecordOut:
    s = stores.get(r.store_id) if r.store_id else None
    auto, final = _qtys(r)
    changed = r.status == SyncStatus.CHANGED
    return SyncRecordOut(
        id=r.id, purchase_id=r.purchase_id, purchase_code=purchase_code(r.purchase_id), status=r.status,
        # No store picked yet (an uploaded row whose store isn't in the CRM): show what the sheet said.
        store_id=r.store_id, outlet_code=s.external_code if s else r.current_source.get("store_code"),
        outlet_name=s.name if s else r.current_source.get("store_name"),
        purchase_date=r.purchase_date, amount=r.amount, price_per_item=r.price_per_item, auto_qty=auto, final_qty=final,
        overridden=r.final_qty_override is not None and r.final_qty_override != auto,
        reason=r.current_source.get("reason"), added_by=r.current_source.get("added_by"),
        sync_code=run_codes.get(r.sync_id), applied_qty=r.applied_qty, applied_at=r.applied_at,
        previous_source=SourceSnapshot(**r.baseline) if changed else None,
        current_source=SourceSnapshot(**r.current_source) if changed else None,
        ever_applied=r.applied_qty is not None,
    )


def overview(db: Session, user: User, *, status_filter: str | None, page: int, page_size: int) -> SyncOverview:
    base = select(CashSyncRecord).where(CashSyncRecord.organization_id == user.organization_id)
    counts = dict(db.execute(
        select(CashSyncRecord.status, func.count()).where(CashSyncRecord.organization_id == user.organization_id).group_by(CashSyncRecord.status)
    ).all())
    if status_filter:
        base = base.where(CashSyncRecord.status == status_filter)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(CashSyncRecord.purchase_date.desc(), CashSyncRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    stores = _store_map(db, user, {r.store_id for r in rows})
    run_ids = {r.sync_id for r in rows if r.sync_id}
    run_codes = {i: sync_code(i) for i in run_ids}
    last = _last_run(db, user)
    return SyncOverview(
        last_sync=_summary(db, user, last) if last else None, counts={k: counts.get(k, 0) for k in
        (SyncStatus.PENDING, SyncStatus.CHANGED, SyncStatus.APPLIED, SyncStatus.SKIPPED)},
        items=[_out(r, stores, run_codes) for r in rows], total=total, page=page, page_size=page_size,
    )


def _get(db: Session, user: User, record_id: uuid.UUID, *, lock: bool = False) -> CashSyncRecord:
    stmt = select(CashSyncRecord).where(CashSyncRecord.id == record_id, CashSyncRecord.organization_id == user.organization_id)
    r = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if r is None:
        raise _err(status.HTTP_404_NOT_FOUND, "Record not found.")
    return r


def edit(db: Session, user: User, record_id: uuid.UUID, body: RecordEdit) -> SyncRecordOut:
    r = _get(db, user, record_id, lock=True)
    if r.status == SyncStatus.APPLIED:
        raise _err(status.HTTP_409_CONFLICT, "This purchase has already been applied to the order sheet.")
    data = body.model_dump(exclude_unset=True)
    if "store_id" in data and data["store_id"] is not None:
        if data["store_id"] not in _store_map(db, user, {data["store_id"]}):
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "That store doesn't exist.")
        r.store_id = data["store_id"]
    if data.get("purchase_date") is not None:
        _check_order_date(data["purchase_date"], allow_any_month=True)
        r.purchase_date = data["purchase_date"]
    if data.get("amount") is not None:
        r.amount = data["amount"]
    if data.get("price_per_item") is not None:
        r.price_per_item = data["price_per_item"]
    if "final_qty" in data:
        r.final_qty_override = data["final_qty"]
    # Changing what the quantity is built from drops an old manual override: the quantity recalculates.
    if ("amount" in data or "price_per_item" in data) and "final_qty" not in data:
        r.final_qty_override = None
    db.commit()
    return _out(r, _store_map(db, user, {r.store_id}), {r.sync_id: sync_code(r.sync_id)} if r.sync_id else {})


def set_standard_rate(db: Session, user: User, body: StandardRate) -> StandardRateResult:
    """One price for every purchase still waiting for review (all pages). Applied purchases are never touched.
    A manual quantity override is dropped wherever the price changes, so the quantity recalculates."""
    rows = db.execute(
        select(CashSyncRecord).where(
            CashSyncRecord.organization_id == user.organization_id, CashSyncRecord.status == SyncStatus.PENDING
        ).with_for_update()
    ).scalars().all()
    updated = kept = 0
    for r in rows:
        if r.price_per_item is not None and not body.overwrite:
            kept += 1
            continue
        if r.price_per_item != body.price_per_item:
            r.final_qty_override = None
        r.price_per_item = body.price_per_item
        updated += 1
    activity_service.record(
        db, actor=user, action="cash_sync.standard_rate", entity_type="cash_sync", entity_id=user.id,
        metadata={"price": str(body.price_per_item), "overwrite": body.overwrite, "updated": updated, "kept": kept},
    )
    db.commit()
    return StandardRateResult(updated=updated, kept=kept)


def resolve(db: Session, user: User, record_id: uuid.UUID, action: str) -> SyncRecordOut:
    r = _get(db, user, record_id, lock=True)
    src = r.current_source
    ever = r.applied_qty is not None
    if action in ("accept_source", "keep_mine", "acknowledge", "reopen") and r.status != SyncStatus.CHANGED:
        raise _err(status.HTTP_409_CONFLICT, "Only a changed record needs that decision.")
    if action == "accept_source":
        if ever:
            raise _err(status.HTTP_409_CONFLICT, "This record was already applied: acknowledge the change or reopen it instead.")
        r.store_id = uuid.UUID(src["store_id"]) if src.get("store_id") else None
        r.purchase_date = date.fromisoformat(src["purchase_date"])
        r.amount = Decimal(src["amount"])
        r.final_qty_override = None
        r.baseline, r.status = src, SyncStatus.PENDING
    elif action == "keep_mine":
        if ever:
            raise _err(status.HTTP_409_CONFLICT, "This record was already applied: acknowledge the change or reopen it instead.")
        r.baseline, r.status = src, SyncStatus.PENDING
    elif action == "acknowledge":
        if not ever:
            raise _err(status.HTTP_409_CONFLICT, "This record was never applied.")
        r.baseline, r.status = src, SyncStatus.APPLIED   # keep what was applied; the new source values are noted, not added
    elif action == "reopen":
        if not ever:
            raise _err(status.HTTP_409_CONFLICT, "This record was never applied.")
        # A deliberate extra adjustment: back to review with the new source values and no quantity yet.
        r.store_id = uuid.UUID(src["store_id"]) if src.get("store_id") else None
        r.purchase_date = date.fromisoformat(src["purchase_date"])
        r.amount = Decimal(src["amount"])
        r.final_qty_override = None
        r.baseline, r.status = src, SyncStatus.PENDING
    elif action == "skip":
        if r.status not in (SyncStatus.PENDING, SyncStatus.CHANGED) or ever:
            raise _err(status.HTTP_409_CONFLICT, "Only a record that hasn't been applied can be skipped.")
        r.baseline, r.status = src, SyncStatus.SKIPPED
    elif action == "unskip":
        if r.status != SyncStatus.SKIPPED:
            raise _err(status.HTTP_409_CONFLICT, "This record isn't skipped.")
        r.status = SyncStatus.PENDING
    activity_service.record(
        db, actor=user, action=f"cash_sync.{action}", entity_type="cash_sync_record", entity_id=r.id,
        metadata={"purchase": purchase_code(r.purchase_id)},
    )
    db.commit()
    return _out(r, _store_map(db, user, {r.store_id}), {r.sync_id: sync_code(r.sync_id)} if r.sync_id else {})


# --------------------------------------------------------------------------
# preview + apply
# --------------------------------------------------------------------------

def _validate(db: Session, user: User, records: list[CashSyncRecord]) -> tuple[list[SyncPreviewRow], dict]:
    """Group the records by (store, date), sum the quantities, read what the sheet holds now, flag problems."""
    stores = _store_map(db, user, {r.store_id for r in records})
    groups: dict[tuple, list[CashSyncRecord]] = {}
    for r in sorted(records, key=lambda x: (x.created_at, x.purchase_id)):   # oldest first: a stable order for the history
        groups.setdefault((r.store_id, r.purchase_date), []).append(r)

    entries: dict[tuple, OrderEntry] = {}
    sids = {k[0] for k in groups if k[0]}
    if sids:
        for e in db.execute(select(OrderEntry).where(OrderEntry.store_id.in_(sids))).scalars():
            if (e.store_id, e.order_date) in groups:
                entries[(e.store_id, e.order_date)] = e

    rows: list[SyncPreviewRow] = []
    for (sid, day), recs in groups.items():
        s = stores.get(sid) if sid else None
        e = entries.get((sid, day))
        previous = e.bottle_count if e else 0
        real = (e.bottle_count - e.cash_adjustment) if e else None
        purchases, added, row_error = [], 0, None
        for r in recs:
            auto, final = _qtys(r)
            err = None
            if r.status != SyncStatus.PENDING:
                err = {"APPLIED": "Already applied to the order sheet.", "CHANGED": "The source changed: review it first.",
                       "SKIPPED": "Skipped."}.get(r.status, "Not ready.")
            elif r.price_per_item is None:
                err = "Enter the price per item."
            elif final is None or final < 1:
                err = "The final quantity must be at least 1."
            elif final > settings.MAX_BOTTLE_COUNT:
                err = f"The quantity can't be more than {settings.MAX_BOTTLE_COUNT}."
            purchases.append(SyncPreviewPurchase(
                record_id=r.id, purchase_code=purchase_code(r.purchase_id), amount=r.amount, price_per_item=r.price_per_item,
                auto_qty=auto, final_qty=final, error=err,
            ))
            added += final if (final and not err) else 0
        if s is None:
            row_error = "Pick the store for this purchase."
        elif s.status != StoreStatus.LIVE.value:
            row_error = "This store isn't live, so it can't take orders."
        elif previous + added > settings.MAX_BOTTLE_COUNT:
            row_error = f"The new total ({previous + added}) is more than {settings.MAX_BOTTLE_COUNT}."
        else:
            try:
                _check_order_date(day, allow_any_month=True)
            except HTTPException as exc:
                row_error = exc.detail
        if row_error is None and any(p.error for p in purchases):
            row_error = next(p.error for p in purchases if p.error)
        rows.append(SyncPreviewRow(
            store_id=sid, outlet_code=s.external_code if s else "?", outlet_name=s.name if s else "No store", purchase_date=day,
            employee_entry=real if real else None, previous=previous, added=added, new_total=previous + added,
            purchases=purchases, error=row_error,
        ))
    rows.sort(key=lambda x: (x.purchase_date, x.outlet_name))
    return rows, groups


def _load(db: Session, user: User, ids: list[uuid.UUID], *, lock: bool) -> list[CashSyncRecord]:
    stmt = select(CashSyncRecord).where(CashSyncRecord.organization_id == user.organization_id, CashSyncRecord.id.in_(set(ids))).order_by(CashSyncRecord.id)
    recs = list(db.execute(stmt.with_for_update() if lock else stmt).scalars())
    if len(recs) != len(set(ids)):
        raise _err(status.HTTP_404_NOT_FOUND, "Some of those records no longer exist.")
    return recs


def preview(db: Session, user: User, ids: list[uuid.UUID]) -> SyncPreview:
    rows, _ = _validate(db, user, _load(db, user, ids, lock=False))
    return SyncPreview(
        rows=rows, total_stores=len({r.store_id for r in rows if r.store_id}), total_records=sum(len(r.purchases) for r in rows),
        total_qty=sum(r.added for r in rows), can_apply=bool(rows) and all(r.error is None for r in rows),
    )


def apply(db: Session, user: User, ids: list[uuid.UUID]) -> SyncApplyResult:
    recs = _load(db, user, ids, lock=True)            # row-locked: a second click / second tab waits, then sees APPLIED
    rows, groups = _validate(db, user, recs)
    problems = [f"{r.outlet_name} ({r.purchase_date:%d-%b}): {r.error}" for r in rows if r.error]
    if problems:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(problems[:5]))

    stores = _store_map(db, user, {r.store_id for r in recs})
    batch = uuid.uuid4()
    now = datetime.now(timezone.utc)
    applied_rows: list[SyncPreviewRow] = []
    failed: list[SyncApplyFailure] = []
    applied_records = 0
    by_key = {(r.store_id, r.purchase_date): r for r in rows}
    for (sid, day), group in groups.items():
        s = stores[sid]
        qtys = [(r, *_qtys(r)) for r in group]
        total_add = sum(final for _, _, final in qtys)
        try:
            with db.begin_nested():
                previous, new_total, real = apply_to_entry(db, user, s, day, total_add)
                running = previous
                for r, auto, final in qtys:
                    db.add(CashAdjustment(
                        organization_id=user.organization_id, batch_id=batch, store_id=s.id, outlet_code=s.external_code,
                        outlet_name=s.name, purchase_date=day, amount=r.amount, price_per_item=r.price_per_item,
                        auto_qty=auto, final_qty=final, previous_qty=running, final_order_qty=running + final,
                        created_by_user_id=user.id, created_by_name=user.full_name, sync_id=r.sync_id,
                        purchase_id=r.purchase_id, source=SOURCE_NAME, action="Applied",
                    ))
                    running += final
                    r.status, r.applied_batch_id, r.applied_at, r.applied_qty = SyncStatus.APPLIED, batch, now, final
                    r.baseline = r.current_source
                db.flush()
            view = by_key[(sid, day)]
            applied_rows.append(view.model_copy(update={"previous": previous, "new_total": new_total, "employee_entry": real}))
            applied_records += len(group)
        except Exception as exc:  # noqa: BLE001 — report per store/day and carry on with the rest
            failed.append(SyncApplyFailure(
                outlet_code=s.external_code, outlet_name=s.name, purchase_date=day,
                error=exc.detail if isinstance(exc, HTTPException) else "The database rejected this change.",
            ))
    if applied_records:
        activity_service.record(
            db, actor=user, action="cash_sync.applied", entity_type="cash_sync", entity_id=batch,
            metadata={"records": applied_records, "stores": len(applied_rows), "failed": len(failed)},
        )
    db.commit()
    return SyncApplyResult(batch_id=batch, applied_records=applied_records, applied_rows=applied_rows, failed=failed)
