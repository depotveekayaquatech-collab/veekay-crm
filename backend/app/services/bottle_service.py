"""
Bottle QR tracking: unique serial generation, printable labels, IN / OUT scans, replacements and the overdue list.

Rules worth remembering:
  * A serial is random (not sequential) so it can't be guessed or forged, and is unique by a database constraint.
  * Scans are append-only. A scan that breaks the IN -> OUT order is still recorded (never lose a real scan) and carries
    a `warning`; only the bottle's current state follows the NEWEST scan, so late offline re-sends can't rewind it.
  * Overdue = last scan is IN and older than BOTTLE_LOST_AFTER_DAYS. Never-scanned (UNUSED), returned (OUT), retired and deleted
    codes are never overdue — a code that was printed but never used is not a problem.
  * Replacing a damaged QR retires the old serial and creates a new one that inherits where the bottle is.
"""
from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.bottle import Bottle, BottleBatch, BottleScan, BottleStatus, ScanDirection
from app.models.organization import Organization
from app.models.store import Store
from app.models.user import User
from app.schemas.bottle import (
    BatchOut, BottleDetail, BottleList, BottleOut, DeleteResult, ReplaceResult, ScanOut, ScanResult, Summary,
)
from app.services import activity_service

# Crockford base32: no I, L, O, U — nothing that can be misread when a label is typed in by hand.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_FIX = str.maketrans({"O": "0", "I": "1", "L": "1"})
PREFIX = "VK"
CHUNK = 1000
MAX_LABELS_PER_PDF = 2000
_FUTURE_SLACK = timedelta(minutes=10)


def _err(code: int, message: str) -> HTTPException:
    return HTTPException(code, message)


def new_serial() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{PREFIX}-{body[:4]}-{body[4:]}"


def normalize_serial(raw: str) -> str:
    """Accepts 'vk-7f3k-9q2m', 'VK7F3K9Q2M' ... and returns 'VK-7F3K-9Q2M'. Raises 422 for anything else."""
    s = "".join(ch for ch in (raw or "").upper() if ch.isalnum())
    if s.startswith(PREFIX):
        s = s[len(PREFIX):]
    s = s.translate(_FIX)
    if len(s) != 8 or any(ch not in _ALPHABET for ch in s):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "That isn't a valid bottle code.")
    return f"{PREFIX}-{s[:4]}-{s[4:]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------

def _is_overdue(b: Bottle, now: datetime) -> bool:
    return b.status == BottleStatus.AT_STORE and b.last_in_at is not None and b.last_in_at < now - timedelta(days=settings.BOTTLE_LOST_AFTER_DAYS)


def _outs(db: Session, bottles: list[Bottle]) -> list[BottleOut]:
    now = _now()
    store_ids = {b.current_store_id for b in bottles if b.current_store_id}
    related = {i for b in bottles for i in (b.replaces_id, b.replaced_by_id) if i}
    stores = dict(db.execute(select(Store.id, Store.name).where(Store.id.in_(store_ids))).all()) if store_ids else {}
    serials = dict(db.execute(select(Bottle.id, Bottle.serial).where(Bottle.id.in_(related))).all()) if related else {}
    out = []
    for b in bottles:
        at_store = b.status == BottleStatus.AT_STORE and b.last_in_at is not None
        out.append(BottleOut(
            id=b.id, serial=b.serial, status=b.status, store_id=b.current_store_id, store_name=stores.get(b.current_store_id),
            last_in_at=b.last_in_at, last_out_at=b.last_out_at, last_scan_at=b.last_scan_at,
            days_at_store=(now - b.last_in_at).days if at_store else None, overdue=_is_overdue(b, now),
            replaces_serial=serials.get(b.replaces_id), replaced_by_serial=serials.get(b.replaced_by_id),
            retired_at=b.retired_at, retire_reason=b.retire_reason,
        ))
    return out


def _scan_out(s: BottleScan) -> ScanOut:
    return ScanOut(
        id=s.id, direction=s.direction, store_id=s.store_id, store_name=s.store_name, scanned_at=s.scanned_at,
        source=s.source, scanned_by_name=s.scanned_by_name, warning=s.warning,
    )


# --------------------------------------------------------------------------
# generation + labels
# --------------------------------------------------------------------------

def generate_batch(db: Session, user: User, quantity: int, note: str | None) -> BatchOut:
    """Creates `quantity` brand-new, unique serials (UNUSED) and remembers their print order."""
    batch = BottleBatch(
        organization_id=user.organization_id, quantity=quantity, note=(note or "").strip() or None,
        created_by_user_id=user.id, created_by_name=user.full_name,
    )
    db.add(batch)
    db.flush()
    made, seq = 0, 0
    while made < quantity:
        want = min(CHUNK, quantity - made)
        candidates = set()
        while len(candidates) < want:
            candidates.add(new_serial())
        now = _now()
        rows = []
        for s in candidates:
            seq += 1
            rows.append({
                "id": uuid.uuid4(), "organization_id": user.organization_id, "serial": s, "batch_id": batch.id, "seq": seq,
                "status": BottleStatus.UNUSED, "created_at": now, "updated_at": now,
            })
        # The unique constraint is the source of truth: a (vanishingly rare) clash is skipped and re-drawn next round.
        got = db.execute(pg_insert(Bottle).values(rows).on_conflict_do_nothing(index_elements=["serial"]).returning(Bottle.id)).all()
        made += len(got)
    db.commit()
    return _batch_out(db, batch)


def _batch_out(db: Session, batch: BottleBatch) -> BatchOut:
    first = db.execute(select(Bottle.serial).where(Bottle.batch_id == batch.id).order_by(Bottle.seq.asc()).limit(1)).scalar()
    last = db.execute(select(Bottle.serial).where(Bottle.batch_id == batch.id).order_by(Bottle.seq.desc()).limit(1)).scalar()
    return BatchOut(
        id=batch.id, quantity=batch.quantity, note=batch.note, created_by_name=batch.created_by_name,
        created_at=batch.created_at, first_serial=first, last_serial=last,
    )


def list_batches(db: Session, user: User, limit: int = 50) -> list[BatchOut]:
    rows = db.execute(
        select(BottleBatch).where(BottleBatch.organization_id == user.organization_id).order_by(BottleBatch.created_at.desc()).limit(limit)
    ).scalars().all()
    return [_batch_out(db, b) for b in rows]


def _get_batch(db: Session, user: User, batch_id: uuid.UUID) -> BottleBatch:
    batch = db.get(BottleBatch, batch_id)
    if batch is None or batch.organization_id != user.organization_id:
        raise _err(status.HTTP_404_NOT_FOUND, "Batch not found.")
    return batch


def batch_csv(db: Session, user: User, batch_id: uuid.UUID) -> bytes:
    """Every serial of the batch in print order — for an external label printer."""
    _get_batch(db, user, batch_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["no", "serial"])
    for seq, serial in db.execute(select(Bottle.seq, Bottle.serial).where(Bottle.batch_id == batch_id).order_by(Bottle.seq)).yield_per(5000):
        w.writerow([seq, serial])
    return buf.getvalue().encode("utf-8")


def labels_pdf(db: Session, user: User, batch_id: uuid.UUID, start: int, count: int) -> bytes:
    """A sheet of printable labels (QR + serial) for `count` bottles of the batch, from print position `start`."""
    batch = _get_batch(db, user, batch_id)
    count = min(count, MAX_LABELS_PER_PDF)
    serials = [r[0] for r in db.execute(
        select(Bottle.serial).where(Bottle.batch_id == batch.id, Bottle.seq >= start).order_by(Bottle.seq).limit(count)
    ).all()]
    if not serials:
        raise _err(status.HTTP_404_NOT_FOUND, "No labels in that range.")
    return render_labels(serials)


def render_labels(serials: list[str]) -> bytes:
    import qrcode
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    cols, rows = 4, 10
    page_w, page_h = A4
    cell_w, cell_h = page_w / cols, page_h / rows
    qr_size = 19 * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    per_page = cols * rows
    for i, serial in enumerate(serials):
        if i and i % per_page == 0:
            c.showPage()
        slot = i % per_page
        x0 = (slot % cols) * cell_w
        y0 = page_h - (slot // cols + 1) * cell_h
        qr = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(serial)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        n = len(matrix)
        mod = qr_size / n
        qx, qy = x0 + (cell_w - qr_size) / 2, y0 + cell_h - qr_size - 2.5 * mm
        c.setFillColorRGB(0, 0, 0)
        for r, row in enumerate(matrix):          # vector squares: crisp at any print size and fast for thousands
            for col, dark in enumerate(row):
                if dark:
                    c.rect(qx + col * mod, qy + (n - 1 - r) * mod, mod + 0.05, mod + 0.05, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x0 + cell_w / 2, qy - 3.6 * mm, serial)
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.3)
        c.rect(x0 + 1.5 * mm, y0 + 1 * mm, cell_w - 3 * mm, cell_h - 2 * mm, stroke=1, fill=0)
    c.save()
    return buf.getvalue()


def replacement_label_pdf(serial: str) -> bytes:
    return render_labels([serial])


# --------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------

def _get_bottle(db: Session, org_id: uuid.UUID, serial: str, *, lock: bool = False) -> Bottle:
    stmt = select(Bottle).where(Bottle.serial == normalize_serial(serial), Bottle.organization_id == org_id)
    if lock:
        stmt = stmt.with_for_update()
    b = db.execute(stmt).scalar_one_or_none()
    if b is None:
        raise _err(status.HTTP_404_NOT_FOUND, "This code isn't one of ours — it was never generated here.")
    return b


def find_store(db: Session, org_id: uuid.UUID, *, store_id: uuid.UUID | None = None, code: str | None = None, platform: str | None = None) -> Store:
    if store_id is not None:
        store = db.get(Store, store_id)
        if store is None or store.organization_id != org_id:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Store not found.")
        return store
    code = (code or "").strip()
    if not code:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say which store: send store_code.")
    stmt = select(Store).where(Store.organization_id == org_id, func.lower(Store.external_code) == code.lower())
    if platform and platform.strip():
        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == platform.strip().lower())
    matches = list(db.execute(stmt).scalars().all())
    if not matches:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No store with code '{code}'.")
    if len(matches) > 1:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Store code '{code}' exists on more than one platform — also send \"platform\".")
    return matches[0]


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def scan(
    db: Session, org_id: uuid.UUID, *, serial: str, direction: str, store: Store | None, scanned_at: datetime | None,
    scan_id: str | None, source: str, user: User | None = None, scanned_by: str | None = None,
) -> ScanResult:
    when = scanned_at or _now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when > _now() + _FUTURE_SLACK:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "The scan time is in the future.")

    if scan_id:
        prior = db.execute(select(BottleScan).where(BottleScan.client_scan_id == scan_id, BottleScan.organization_id == org_id)).scalar_one_or_none()
        if prior is not None:
            return _duplicate(db, prior)

    b = _get_bottle(db, org_id, serial, lock=True)
    if b.status == BottleStatus.DELETED:
        raise _err(status.HTTP_409_CONFLICT, f"{b.serial} has been deleted and can never be scanned.")
    if b.status == BottleStatus.RETIRED:
        hint = ""
        if b.replaced_by_id:
            new = db.get(Bottle, b.replaced_by_id)
            hint = f" It was replaced by {new.serial}." if new else ""
        raise _err(status.HTTP_409_CONFLICT, f"{b.serial} has been retired and can't be scanned.{hint}")

    if direction == ScanDirection.IN and store is None:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the store the bottle is arriving at.")
    if direction == ScanDirection.OUT and store is None and b.current_store_id:
        store = db.get(Store, b.current_store_id)

    warning = None
    if direction == ScanDirection.IN and b.status == BottleStatus.AT_STORE:
        where = db.get(Store, b.current_store_id).name if b.current_store_id else "a store"
        warning = f"Already scanned IN at {where} with no OUT scan since."
    elif direction == ScanDirection.OUT and b.status != BottleStatus.AT_STORE:
        warning = "No IN scan was recorded before this OUT."

    row = BottleScan(
        organization_id=org_id, bottle_id=b.id, serial=b.serial, direction=direction,
        store_id=store.id if store else None, store_name=store.name if store else None, scanned_at=when, source=source,
        scanned_by_user_id=user.id if user else None, scanned_by_name=(user.full_name if user else scanned_by),
        client_scan_id=scan_id, warning=warning,
    )
    db.add(row)
    # The bottle's state follows the newest scan only, so a late offline re-send can't rewind it.
    if b.last_scan_at is None or when >= b.last_scan_at:
        b.last_scan_at = when
        if direction == ScanDirection.IN:
            b.status, b.current_store_id, b.last_in_at = BottleStatus.AT_STORE, store.id, when
        else:
            b.status, b.last_out_at = BottleStatus.RETURNED, when
            b.current_store_id = store.id if store else b.current_store_id
    elif direction == ScanDirection.IN:
        b.last_in_at = max(b.last_in_at or when, when)
    else:
        b.last_out_at = max(b.last_out_at or when, when)
    try:
        db.commit()
    except IntegrityError:           # the same scan_id arrived twice at once
        db.rollback()
        prior = db.execute(select(BottleScan).where(BottleScan.client_scan_id == scan_id)).scalar_one_or_none()
        if prior is None:
            raise
        return _duplicate(db, prior)
    db.refresh(b)
    return ScanResult(warning=warning, bottle=_outs(db, [b])[0], scan=_scan_out(row))


def _duplicate(db: Session, prior: BottleScan) -> ScanResult:
    b = db.get(Bottle, prior.bottle_id)
    return ScanResult(duplicate=True, warning=prior.warning, bottle=_outs(db, [b])[0], scan=_scan_out(prior))


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def detail(db: Session, org_id: uuid.UUID, serial: str) -> BottleDetail:
    b = _get_bottle(db, org_id, serial)
    scans = db.execute(select(BottleScan).where(BottleScan.bottle_id == b.id).order_by(BottleScan.scanned_at.desc()).limit(500)).scalars().all()
    return BottleDetail(bottle=_outs(db, [b])[0], scans=[_scan_out(s) for s in scans])


def summary(db: Session, user: User) -> Summary:
    org = user.organization_id
    counts = dict(db.execute(select(Bottle.status, func.count()).where(Bottle.organization_id == org).group_by(Bottle.status)).all())
    cutoff = _now() - timedelta(days=settings.BOTTLE_LOST_AFTER_DAYS)
    overdue = db.execute(select(func.count()).where(
        Bottle.organization_id == org, Bottle.status == BottleStatus.AT_STORE, Bottle.last_in_at < cutoff)).scalar_one()
    retired = counts.get(BottleStatus.RETIRED, 0)
    deleted = counts.get(BottleStatus.DELETED, 0)
    return Summary(
        total_active=sum(counts.values()) - retired - deleted, unused=counts.get(BottleStatus.UNUSED, 0), at_store=counts.get(BottleStatus.AT_STORE, 0),
        returned=counts.get(BottleStatus.RETURNED, 0), retired=retired, deleted=deleted, overdue=overdue, lost_after_days=settings.BOTTLE_LOST_AFTER_DAYS,
    )


def search(
    db: Session, org_id: uuid.UUID, *, q: str | None = None, state: str | None = None, store_id: uuid.UUID | None = None,
    overdue_days: int | None = None, page: int = 1, page_size: int = 50,
) -> BottleList:
    """state: UNUSED / AT_STORE / RETURNED / RETIRED / DELETED / OVERDUE. `overdue_days` overrides the default threshold."""
    conds = [Bottle.organization_id == org_id]
    if state == "OVERDUE":
        days = overdue_days if overdue_days is not None else settings.BOTTLE_LOST_AFTER_DAYS
        conds += [Bottle.status == BottleStatus.AT_STORE, Bottle.last_in_at < _now() - timedelta(days=days)]
    elif state:
        conds.append(Bottle.status == state)
    else:
        conds.append(Bottle.status != BottleStatus.DELETED)     # deleted codes show only when asked for
    if store_id:
        conds.append(Bottle.current_store_id == store_id)
    if q and q.strip():
        conds.append(Bottle.serial.ilike(f"%{q.strip().upper()}%"))
    total = db.execute(select(func.count()).select_from(Bottle).where(*conds)).scalar_one()
    order = Bottle.last_in_at.asc() if state == "OVERDUE" else Bottle.created_at.desc()   # oldest-missing first
    rows = db.execute(select(Bottle).where(*conds).order_by(order, Bottle.serial).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return BottleList(items=_outs(db, list(rows)), total=total, page=page, page_size=page_size)


# --------------------------------------------------------------------------
# replace / retire
# --------------------------------------------------------------------------

def replace(db: Session, user: User, serial: str, reason: str | None) -> tuple[ReplaceResult, str]:
    """Damaged / unreadable QR: retire it and issue a new serial that inherits where the bottle is."""
    old = _get_bottle(db, user.organization_id, serial, lock=True)
    if old.status in (BottleStatus.RETIRED, BottleStatus.DELETED):
        raise _err(status.HTTP_409_CONFLICT, f"{old.serial} is already {old.status.lower()}.")
    new = None
    for _ in range(5):
        candidate = new_serial()
        try:
            with db.begin_nested():
                new = Bottle(
                    organization_id=old.organization_id, serial=candidate, status=old.status, current_store_id=old.current_store_id,
                    last_in_at=old.last_in_at, last_out_at=old.last_out_at, last_scan_at=old.last_scan_at, replaces_id=old.id,
                )
                db.add(new)
                db.flush()
            break
        except IntegrityError:
            new = None
    if new is None:
        raise _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Couldn't generate a unique code; try again.")
    old.status, old.retired_at, old.replaced_by_id = BottleStatus.RETIRED, _now(), new.id
    old.retire_reason = (reason or "").strip() or "QR damaged — replaced"
    db.commit()
    db.refresh(old)
    db.refresh(new)
    olds, news = _outs(db, [old, new])
    return ReplaceResult(old=olds, new=news), new.serial


def retire(db: Session, user: User, serial: str, reason: str | None) -> BottleOut:
    """Write a bottle off (destroyed / confirmed lost) without issuing a replacement."""
    b = _get_bottle(db, user.organization_id, serial, lock=True)
    if b.status in (BottleStatus.RETIRED, BottleStatus.DELETED):
        raise _err(status.HTTP_409_CONFLICT, f"{b.serial} is already {b.status.lower()}.")
    b.status, b.retired_at = BottleStatus.RETIRED, _now()
    b.retire_reason = (reason or "").strip() or "Retired"
    db.commit()
    db.refresh(b)
    return _outs(db, [b])[0]


def scan_stores(db: Session, user: User) -> list[dict]:
    from app.models.store import StoreStatus

    rows = db.execute(
        select(Store.id, Store.name, Store.external_code, Store.city).where(
            Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value).order_by(Store.name)
    ).all()
    return [{"id": r[0], "name": r[1], "code": r[2], "city": r[3]} for r in rows]


# --------------------------------------------------------------------------
# delete (developer only) — the code stops working for good, its history stays
# --------------------------------------------------------------------------

def _void(db: Session, user: User, bottles: list[Bottle], reason: str | None, not_found: list[str], what: str, skipped_in_use: list[str] | None = None) -> DeleteResult:
    """Marks the codes DELETED: they can never be scanned again, can't be re-issued (the serial stays taken), and every
    record and scan stays on file — a deleted code is still searchable, with its full history."""
    doomed = [b for b in bottles if b.status != BottleStatus.DELETED]
    if doomed:
        now = _now()
        text = (reason or "").strip() or "Deleted"
        for b in doomed:
            b.status, b.retired_at, b.retire_reason = BottleStatus.DELETED, now, text
        activity_service.record(
            db, actor=user, action="bottle.deleted", entity_type="bottle", entity_id=doomed[0].serial,
            metadata={"what": what, "count": len(doomed), "reason": text, "serials": [b.serial for b in doomed[:200]]},
        )
    db.commit()
    return DeleteResult(
        deleted=len(doomed), already_deleted=len(bottles) - len(doomed), skipped_in_use=(skipped_in_use or [])[:200], not_found=not_found[:200],
    )


def delete_serials(db: Session, user: User, serials: list[str], reason: str | None) -> DeleteResult:
    wanted, bad = [], []
    for raw in serials:
        try:
            wanted.append(normalize_serial(raw))
        except HTTPException:
            bad.append(raw.strip()[:40])
    wanted = list(dict.fromkeys(wanted))
    found = list(db.execute(select(Bottle).where(Bottle.organization_id == user.organization_id, Bottle.serial.in_(wanted)).with_for_update()).scalars().all()) if wanted else []
    have = {b.serial for b in found}
    return _void(db, user, found, reason, bad + [s for s in wanted if s not in have], f"{len(wanted)} code(s)")


def delete_batch(db: Session, user: User, batch_id: uuid.UUID, reason: str | None) -> DeleteResult:
    """Voids a batch's codes that were never used. Codes already in circulation (scanned) are left alone — delete those one by one."""
    _get_batch(db, user, batch_id)
    found = list(db.execute(select(Bottle).where(Bottle.batch_id == batch_id).with_for_update()).scalars().all())
    unused = [b for b in found if b.status in (BottleStatus.UNUSED, BottleStatus.DELETED)]
    in_use = [b.serial for b in found if b not in unused and b.status != BottleStatus.RETIRED]
    return _void(db, user, unused, reason, [], f"batch {batch_id}", in_use)
