"""
Store compliance cards and monthly bills.

Rules (from the original system):
  - Months selectable from COMPLIANCE_EARLIEST_MONTH, at most 12 back, never future.
  - One file is stored as-is; two or more photos are merged into one PDF;
    a PDF must be uploaded alone. Max COMPLIANCE_MAX_FILE_MB per file.
  - One document per (store, month, kind). A new upload REPLACES the old file;
    for bills the cleared status survives a re-upload.
  - A bill is due at month-end + BILL_DUE_DAYS_AFTER_MONTH_END (45) days.
  - Employees only touch stores assigned to them; admins (compliance.manage)
    any store; accountants (accounts.view) may view any document.
"""
from __future__ import annotations

import calendar
import io
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core import storage
from app.core.config import settings
from app.models.compliance_document import BillStatus, ComplianceDocument, DocKind
from app.models.organization import Organization
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.schemas.compliance import (
    ComplianceStorePage, ComplianceStoreRow, DocBrief, DueBill, DueBills, SearchPage, SearchRow,
)
from app.services import activity_service, assignment_service

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
MAX_FILES_PER_UPLOAD = 20
MAX_IMAGE_PIXELS = 60_000_000
MAX_DIMENSION = 2400  # photos are downscaled so merged PDFs stay small


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _err(code: int, msg: str) -> HTTPException:
    return HTTPException(code, msg)


# --------------------------------------------------------------------------
# months
# --------------------------------------------------------------------------

def allowed_months(today: date | None = None) -> list[date]:
    """First-of-month dates, newest first."""
    today = today or _today()
    ey, em = (int(x) for x in settings.COMPLIANCE_EARLIEST_MONTH.split("-"))
    earliest = date(ey, em, 1)
    out: list[date] = []
    y, m = today.year, today.month
    for _ in range(settings.COMPLIANCE_MAX_MONTHS_BACK + 1):
        d = date(y, m, 1)
        if d < earliest:
            break
        out.append(d)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out or [date(today.year, today.month, 1)]


def parse_month(value: str | None) -> date:
    months = allowed_months()
    if not value:
        return months[0]
    try:
        y, m = (int(x) for x in value.split("-"))
        d = date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-09.") from exc
    if d not in months:
        raise _err(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Month must be between {months[-1]:%Y-%m} and {months[0]:%Y-%m}.",
        )
    return d


def month_label(d: date) -> str:
    return f"{_MONTHS[d.month]} {d.year}"


def bill_due_date(month: date) -> date:
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    return end + timedelta(days=settings.BILL_DUE_DAYS_AFTER_MONTH_END)


# --------------------------------------------------------------------------
# access
# --------------------------------------------------------------------------

def _can_manage(perms: set[str]) -> bool:
    return "compliance.manage" in perms


def _can_view_any(perms: set[str]) -> bool:
    return "compliance.manage" in perms or "accounts.view" in perms


def _store_for_write(db: Session, user: User, perms: set[str], store_id: uuid.UUID) -> Store:
    store = db.execute(
        select(Store)
        .where(Store.id == store_id, Store.organization_id == user.organization_id)
        .options(joinedload(Store.partner_organization))
    ).unique().scalar_one_or_none()
    if store is None:
        raise _err(status.HTTP_404_NOT_FOUND, "Store not found.")
    if not _can_manage(perms) and store.id not in assignment_service.visible_store_ids(db, user):
        raise _err(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
    return store


def _doc_for_access(db: Session, user: User, perms: set[str], doc_id: uuid.UUID, *, write: bool) -> ComplianceDocument:
    doc = db.get(ComplianceDocument, doc_id)
    if doc is None or doc.organization_id != user.organization_id:
        raise _err(status.HTTP_404_NOT_FOUND, "Document not found.")
    if _can_manage(perms) or (not write and _can_view_any(perms)):
        return doc
    if doc.store_id not in assignment_service.visible_store_ids(db, user):
        raise _err(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
    return doc


# --------------------------------------------------------------------------
# file handling
# --------------------------------------------------------------------------

def _sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


_CONTENT_TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _merge_images_to_pdf(images: list[bytes]) -> bytes:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Image support (Pillow) is not installed.") from exc
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    pages = []
    try:
        for raw in images:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
            pages.append(img.convert("RGB"))
        out = io.BytesIO()
        pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
        return out.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "One of the photos could not be read.") from exc


def _prepare(files: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    """(bytes_to_store, extension) applying the one-file / merge / PDF-alone rules."""
    if not files:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one file.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Upload at most {MAX_FILES_PER_UPLOAD} files at once.")
    limit = settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024
    kinds: list[str] = []
    for name, data in files:
        if not data:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{name}' is empty.")
        if len(data) > limit:
            raise _err(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"'{name}' is larger than {settings.COMPLIANCE_MAX_FILE_MB} MB.")
        kind = _sniff(data)
        if kind is None:
            raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{name}' must be a JPG, PNG, WEBP photo or a PDF.")
        kinds.append(kind)
    if "pdf" in kinds and len(files) > 1:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "A PDF must be uploaded on its own (not together with other files).")
    if len(files) == 1:
        return files[0][1], kinds[0]
    return _merge_images_to_pdf([d for _, d in files]), "pdf"


def _key_for(store: Store, month: date, kind: str, ext: str) -> str:
    """<Month Year>/<STATE>/<ENTITY>/<code>-<kind>.<ext>; bills under Bills/; Zepto has no entity level."""
    segs = [month_label(month), (store.state or "Unknown").upper()]
    platform_slug = store.partner_organization.slug if store.partner_organization else None
    if store.entity and not assignment_service.is_employee_model(platform_slug):
        segs.append(store.entity.upper())
    folder = "/".join(storage.safe_segment(x) for x in segs)
    prefix = "Bills/" if kind == DocKind.BILL.value else ""
    return f"{prefix}{folder}/{storage.safe_segment(store.external_code)}-{kind}.{ext}"


# --------------------------------------------------------------------------
# upload / remove / clear
# --------------------------------------------------------------------------

def _brief(doc: ComplianceDocument, today: date, uploader: str | None = None) -> DocBrief:
    return DocBrief(
        id=doc.id, file_name=doc.file_name, content_type=doc.content_type, size_bytes=doc.size_bytes,
        uploaded_at=doc.updated_at, uploaded_by=uploader,
        due_date=doc.due_date, status=doc.status,
        overdue=bool(doc.kind == DocKind.BILL.value and doc.status == BillStatus.PENDING.value
                     and doc.due_date and doc.due_date <= today),
    )


def upload(
    db: Session, user: User, perms: set[str], store_id: uuid.UUID, month_str: str, kind: str,
    files: list[tuple[str, bytes]],
) -> DocBrief:
    if kind not in (DocKind.CARD.value, DocKind.BILL.value):
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "kind must be 'card' or 'bill'.")
    month = parse_month(month_str)
    store = _store_for_write(db, user, perms, store_id)
    data, ext = _prepare(files)

    key = _key_for(store, month, kind, ext)
    storage.save(key, data)

    doc = db.execute(
        select(ComplianceDocument).where(
            ComplianceDocument.store_id == store.id, ComplianceDocument.month == month,
            ComplianceDocument.kind == kind,
        )
    ).scalar_one_or_none()
    old_key = None
    display = f"{store.external_code}_{kind}_{month:%Y-%m}.{ext}"
    if doc is None:
        doc = ComplianceDocument(
            organization_id=user.organization_id, store_id=store.id, month=month, kind=kind,
            file_key=key, file_name=display, content_type=_CONTENT_TYPES[ext], size_bytes=len(data),
            uploaded_by_user_id=user.id,
            due_date=bill_due_date(month) if kind == DocKind.BILL.value else None,
            status=BillStatus.PENDING.value if kind == DocKind.BILL.value else None,
        )
        db.add(doc)
    else:  # replace in place; bills keep their cleared status
        old_key = doc.file_key
        doc.file_key, doc.file_name = key, display
        doc.content_type, doc.size_bytes = _CONTENT_TYPES[ext], len(data)
        doc.uploaded_by_user_id = user.id
        if kind == DocKind.BILL.value and doc.due_date is None:
            doc.due_date = bill_due_date(month)
    activity_service.record(
        db, actor=user, action="compliance.uploaded", entity_type="compliance_document", entity_id=store.id,
        metadata={"store": store.name, "code": store.external_code, "month": f"{month:%Y-%m}", "kind": kind,
                  "files": len(files), "replaced": old_key is not None},
    )
    db.commit()
    if old_key and old_key != key:
        storage.delete(old_key)
    db.refresh(doc)
    return _brief(doc, _today(), user.full_name)


def remove(db: Session, user: User, perms: set[str], doc_id: uuid.UUID) -> None:
    doc = _doc_for_access(db, user, perms, doc_id, write=True)
    key, store_id, kind, month = doc.file_key, doc.store_id, doc.kind, doc.month
    db.delete(doc)
    activity_service.record(
        db, actor=user, action="compliance.removed", entity_type="compliance_document", entity_id=store_id,
        metadata={"month": f"{month:%Y-%m}", "kind": kind},
    )
    db.commit()
    storage.delete(key)


def clear_bill(db: Session, user: User, doc_id: uuid.UUID) -> DocBrief:
    doc = db.get(ComplianceDocument, doc_id)
    if doc is None or doc.organization_id != user.organization_id:
        raise _err(status.HTTP_404_NOT_FOUND, "Document not found.")
    if doc.kind != DocKind.BILL.value:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only bills can be marked cleared.")
    if doc.status != BillStatus.CLEARED.value:
        doc.status = BillStatus.CLEARED.value
        doc.cleared_at = datetime.now(timezone.utc)
        doc.cleared_by_user_id = user.id
        activity_service.record(
            db, actor=user, action="bill.cleared", entity_type="compliance_document", entity_id=doc.store_id,
            metadata={"month": f"{doc.month:%Y-%m}"},
        )
        db.commit()
        db.refresh(doc)
    return _brief(doc, _today())


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def read_file(db: Session, user: User, perms: set[str], doc_id: uuid.UUID) -> tuple[bytes, str, str]:
    doc = _doc_for_access(db, user, perms, doc_id, write=False)
    if not storage.exists(doc.file_key):
        raise _err(status.HTTP_404_NOT_FOUND, "The file is missing from storage. Please upload it again.")
    return storage.read(doc.file_key), doc.content_type, doc.file_name


def zip_docs(db: Session, user: User, perms: set[str], ids: list[uuid.UUID]) -> bytes:
    if not _can_view_any(perms):
        raise _err(status.HTTP_403_FORBIDDEN, "You don't have permission to download documents.")
    docs = db.execute(
        select(ComplianceDocument)
        .where(ComplianceDocument.id.in_(ids), ComplianceDocument.organization_id == user.organization_id)
        .options(joinedload(ComplianceDocument.store).joinedload(Store.partner_organization))
    ).unique().scalars().all()
    if not docs:
        raise _err(status.HTTP_404_NOT_FOUND, "No documents found.")
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            if not storage.exists(d.file_key):
                continue
            st = d.store
            base = "/".join([
                storage.safe_segment(month_label(d.month)),
                storage.safe_segment((st.state or "Unknown").upper()),
                storage.safe_segment(f"{st.name} ({st.external_code}) - {d.kind}"),
            ])
            ext = d.file_name.rsplit(".", 1)[-1]
            name, n = f"{base}.{ext}", 1
            while name in used:
                n += 1
                name = f"{base} ({n}).{ext}"
            used.add(name)
            zf.writestr(name, storage.read(d.file_key))
    return buf.getvalue()


def _store_filters(stmt, *, partner: str | None, q: str | None, entity: str | None = None,
                   state: str | None = None, city: str | None = None, vendor: str | None = None):
    if partner:
        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
    if entity:
        stmt = stmt.where(func.lower(Store.entity) == entity.lower())
    if state:
        stmt = stmt.where(func.lower(Store.state) == state.lower())
    if city:
        stmt = stmt.where(Store.city.ilike(f"%{city.strip()}%"))
    if vendor:
        stmt = stmt.where(Store.vendor_name.ilike(f"%{vendor.strip()}%"))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Store.name.ilike(like), Store.external_code.ilike(like)))
    return stmt


def _docs_by_store(db: Session, store_ids: list[uuid.UUID], month: date) -> dict[uuid.UUID, dict[str, ComplianceDocument]]:
    if not store_ids:
        return {}
    out: dict[uuid.UUID, dict[str, ComplianceDocument]] = {}
    for d in db.execute(
        select(ComplianceDocument).where(ComplianceDocument.store_id.in_(store_ids), ComplianceDocument.month == month)
    ).scalars():
        out.setdefault(d.store_id, {})[d.kind] = d
    return out


def list_stores(
    db: Session, user: User, perms: set[str], *, month_str: str | None, partner: str | None,
    q: str | None, page: int, page_size: int,
) -> ComplianceStorePage:
    month = parse_month(month_str)
    today = _today()
    if _can_manage(perms):
        stmt = _store_filters(
            select(Store).where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value),
            partner=partner, q=q,
        ).options(joinedload(Store.partner_organization)).order_by(Store.name)
        stores = db.execute(stmt).unique().scalars().all()
    else:
        ql = (q or "").strip().lower()
        stores = sorted(
            (s for s in assignment_service.visible_stores(db, user)
             if (not partner or (s.partner_organization and s.partner_organization.slug == partner))
             and (not ql or ql in s.name.lower() or ql in s.external_code.lower())),
            key=lambda s: s.name.lower(),
        )

    docs = _docs_by_store(db, [s.id for s in stores], month)
    cards = sum(1 for s in stores if DocKind.CARD.value in docs.get(s.id, {}))
    bills = [docs.get(s.id, {}).get(DocKind.BILL.value) for s in stores]
    start = (page - 1) * page_size
    items = []
    for s in stores[start:start + page_size]:
        d = docs.get(s.id, {})
        items.append(ComplianceStoreRow(
            store_id=s.id, name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            platform_slug=s.partner_organization.slug if s.partner_organization else None,
            entity=s.entity, state=s.state, city=s.city, vendor_name=s.vendor_name,
            card=_brief(d[DocKind.CARD.value], today) if DocKind.CARD.value in d else None,
            bill=_brief(d[DocKind.BILL.value], today) if DocKind.BILL.value in d else None,
        ))
    return ComplianceStorePage(
        month=f"{month:%Y-%m}", month_label=month_label(month),
        months=[f"{m:%Y-%m}" for m in allowed_months()],
        items=items, total=len(stores), page=page, page_size=page_size,
        cards_done=cards,
        bills_done=sum(1 for b in bills if b is not None),
        bills_pending=sum(1 for b in bills if b is not None and b.status == BillStatus.PENDING.value),
    )


def search(
    db: Session, user: User, *, month_str: str | None, partner: str | None, entity: str | None,
    state: str | None, city: str | None, vendor: str | None, q: str | None, kind: str,
    page: int, page_size: int,
) -> SearchPage:
    month = parse_month(month_str)
    today = _today()
    stmt = _store_filters(
        select(Store).where(Store.organization_id == user.organization_id),
        partner=partner, q=q, entity=entity, state=state, city=city, vendor=vendor,
    ).options(joinedload(Store.partner_organization)).order_by(Store.state, Store.name)
    stores = db.execute(stmt).unique().scalars().all()
    docs = _docs_by_store(db, [s.id for s in stores], month)

    def keep(d: dict[str, ComplianceDocument]) -> bool:
        has_card, has_bill = DocKind.CARD.value in d, DocKind.BILL.value in d
        if kind == "card":
            return has_card
        if kind == "bill":
            return has_bill
        if kind == "both":
            return has_card and has_bill
        return has_card or has_bill

    rows = [s for s in stores if keep(docs.get(s.id, {}))]
    start = (page - 1) * page_size
    items = []
    for s in rows[start:start + page_size]:
        d = docs[s.id]
        items.append(SearchRow(
            store_id=s.id, month=f"{month:%Y-%m}", name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            entity=s.entity, state=s.state, city=s.city, vendor_name=s.vendor_name,
            card=_brief(d[DocKind.CARD.value], today) if DocKind.CARD.value in d else None,
            bill=_brief(d[DocKind.BILL.value], today) if DocKind.BILL.value in d else None,
        ))
    return SearchPage(items=items, total=len(rows), page=page, page_size=page_size)


def due_bills(db: Session, user: User, limit: int = 200) -> DueBills:
    today = _today()
    base = (
        select(ComplianceDocument)
        .where(
            ComplianceDocument.organization_id == user.organization_id,
            ComplianceDocument.kind == DocKind.BILL.value,
            ComplianceDocument.status == BillStatus.PENDING.value,
            ComplianceDocument.due_date <= today,
        )
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    docs = db.execute(
        base.options(joinedload(ComplianceDocument.store).joinedload(Store.partner_organization))
        .order_by(ComplianceDocument.due_date.asc()).limit(limit)
    ).unique().scalars().all()
    return DueBills(total=total, items=[
        DueBill(
            id=d.id, store_id=d.store_id, store_name=d.store.name, external_code=d.store.external_code,
            platform=d.store.partner_organization.name if d.store.partner_organization else None,
            entity=d.store.entity, state=d.store.state, vendor_name=d.store.vendor_name,
            month=f"{d.month:%Y-%m}", due_date=d.due_date, days_overdue=(today - d.due_date).days,
            file_name=d.file_name,
        )
        for d in docs
    ])
