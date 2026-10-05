"""
Store Compliance Repository: the monthly compliance picture for every store.

Per store and month there are three required documents: the compliance card
(kind 'card'), the invoice ('bill') and the proof of payment ('payment'). A store is
  COMPLETE  when all 3 are on file,
  PENDING   when none are,
  PARTIAL   otherwise;
its percent is documents_on_file / 3.

This module builds the filtered / sorted / paged repository view, handles bulk
upload (files matched to stores by the store code in the file name) and the
selected-stores summary PDF. Single-file upload, view, remove and zip live in
compliance_service.
"""
from __future__ import annotations

import io
import re
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core import storage
from app.core.config import settings
from app.models.compliance_document import VALID_KINDS, BillStatus, ComplianceDocument, DocKind
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.schemas.compliance import (
    BulkFailure, BulkUploadResult, ComplianceKpis, ComplianceOptions, ComplianceRow,
    ComplianceStorePage, DocBrief, RegionOption,
)
from app.services import activity_service, assignment_service
from app.services.compliance_service import (
    MAX_FILES_PER_UPLOAD, _brief, _can_manage, _CONTENT_TYPES, _err, _key_for, _prepare, _today, save_document,
    allowed_months, bill_due_date, month_label, parse_month,
)

REQUIRED = (DocKind.CARD.value, DocKind.BILL.value, DocKind.PAYMENT.value)   # the 3 documents that make up compliance
UNASSIGNED = "__none__"
MAX_BULK_FILES = 300
RANGES = {"0-25": (0, 25), "26-50": (26, 50), "51-75": (51, 75), "76-99": (76, 99), "100": (100, 100)}  # with 3 documents: 0, 33, 67, 100


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _accessible_stores(db: Session, user: User, perms: set[str], *, live_only: bool) -> list[Store]:
    if _can_manage(perms):
        stmt = (
            select(Store)
            .where(Store.organization_id == user.organization_id)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
            .order_by(Store.name)
        )
        if live_only:
            stmt = stmt.where(Store.status == StoreStatus.LIVE.value)
        return list(db.execute(stmt).unique().scalars().all())
    rows = assignment_service.visible_stores(db, user)  # visible stores are LIVE by definition
    return sorted(rows, key=lambda s: s.name.lower())


def _docs(db: Session, store_ids: list[uuid.UUID], month: date) -> dict[uuid.UUID, dict[str, ComplianceDocument]]:
    out: dict[uuid.UUID, dict[str, ComplianceDocument]] = {}
    if not store_ids:
        return out
    for d in db.execute(
        select(ComplianceDocument).where(
            ComplianceDocument.store_id.in_(store_ids), ComplianceDocument.month == month, ComplianceDocument.deleted_at.is_(None))
    ).scalars():
        out.setdefault(d.store_id, {})[d.kind] = d
    return out


def _logged(d: dict[str, ComplianceDocument]) -> int:
    return sum(1 for k in REQUIRED if k in d)


def _status(n: int) -> str:
    return "COMPLETE" if n == len(REQUIRED) else ("PENDING" if n == 0 else "PARTIAL")


# --------------------------------------------------------------------------
# repository view
# --------------------------------------------------------------------------

def repository(
    db: Session, user: User, perms: set[str], *, month_str: str | None, partner: str | None, region: uuid.UUID | None,
    city: str | None, manager: str | None, missing: str | None, rng: str | None, status_filter: str | None,
    q: str | None, sort: str, direction: str, page: int, page_size: int,
) -> ComplianceStorePage:
    month = parse_month(month_str)
    today = _today()

    everyone = _accessible_stores(db, user, perms, live_only=True)
    # The "delivery manager" of a store is its vendor — the person/firm that actually delivers to it.
    managers = {s.id: ((s.vendor_name or "").strip() or None) for s in everyone}

    # Dropdown options follow the selected platform (Blinkit and Zepto have their own regions/cities/vendors).
    scoped = [s for s in everyone if not partner or (s.partner_organization and s.partner_organization.slug == partner)]
    options = ComplianceOptions(
        regions=sorted(
            {s.region.id: RegionOption(id=s.region.id, name=s.region.name) for s in scoped if s.region}.values(),
            key=lambda r: r.name.lower(),
        ),
        cities=sorted({s.city.strip() for s in scoped if s.city and s.city.strip()}, key=str.lower),
        managers=sorted({m.lower(): m for m in (managers[s.id] for s in scoped) if m}.values(), key=str.lower),  # one entry per vendor, any spelling/case
        has_unassigned=any(managers[s.id] is None for s in scoped),
    )

    # ---- store-level filters (these also drive the KPI tiles) ----
    ql = (q or "").strip().lower()
    stores = [
        s for s in everyone
        if (not partner or (s.partner_organization and s.partner_organization.slug == partner))
        and (region is None or s.region_id == region)
        and (not city or (s.city or "").strip().lower() == city.strip().lower())
        and (not manager or (managers[s.id] is None if manager == UNASSIGNED else (managers[s.id] or "").lower() == manager.lower()))
        and (not ql or ql in s.name.lower() or ql in s.external_code.lower())
    ]

    docs = _docs(db, [s.id for s in stores], month)
    n = len(stores)
    logged = {k: sum(1 for s in stores if k in docs.get(s.id, {})) for k in REQUIRED}
    kpis = ComplianceKpis(
        total=n,
        card_logged=logged["card"], card_missing=n - logged["card"],
        invoice_logged=logged["bill"], invoice_missing=n - logged["bill"],
        payment_logged=logged["payment"], payment_missing=n - logged["payment"],
        compliance_percent=round(sum(logged.values()) / (n * len(REQUIRED)) * 100, 1) if n else 0.0,
    )

    # ---- document-level filters ----
    def pct(s: Store) -> int:
        return round(_logged(docs.get(s.id, {})) / len(REQUIRED) * 100)

    def keep(s: Store) -> bool:
        d = docs.get(s.id, {})
        st = _status(_logged(d))
        if status_filter and st != status_filter.upper():
            return False
        if rng in RANGES and not (RANGES[rng][0] <= pct(s) <= RANGES[rng][1]):
            return False
        if missing == "any" and st == "COMPLETE":
            return False
        if missing in REQUIRED and missing in d:
            return False
        return True

    rows = [s for s in stores if keep(s)]

    keyfun = {
        "name": lambda s: s.name.lower(),
        "city": lambda s: (s.city or "").lower(),
        "channel": lambda s: (s.partner_organization.name if s.partner_organization else "").lower(),
        "manager": lambda s: (managers[s.id] or "~").lower(),
        "status": lambda s: (_logged(docs.get(s.id, {})), s.name.lower()),
        "percent": lambda s: (_logged(docs.get(s.id, {})), s.name.lower()),
        **{k: (lambda s, k=k: (k in docs.get(s.id, {}), s.name.lower())) for k in REQUIRED},
    }.get(sort, lambda s: s.name.lower())
    rows.sort(key=keyfun, reverse=(direction == "desc"))

    start = (page - 1) * page_size
    items: list[ComplianceRow] = []
    for s in rows[start:start + page_size]:
        d = docs.get(s.id, {})
        n_logged = _logged(d)

        def b(kind: str) -> DocBrief | None:
            return _brief(d[kind], today) if kind in d else None

        items.append(ComplianceRow(
            store_id=s.id, name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            platform_slug=s.partner_organization.slug if s.partner_organization else None,
            entity=s.entity, state=s.state, city=s.city, region_name=s.region.name if s.region else None,
            vendor_name=s.vendor_name, manager=managers[s.id], status=_status(n_logged),
            percent=round(n_logged / len(REQUIRED) * 100), card=b("card"), bill=b("bill"), payment=b("payment"),
        ))

    return ComplianceStorePage(
        month=f"{month:%Y-%m}", month_label=month_label(month), months=[f"{m:%Y-%m}" for m in allowed_months()],
        items=items, total=len(rows), page=page, page_size=page_size, kpis=kpis, options=options,
    )


# --------------------------------------------------------------------------
# bulk upload — files are matched to stores by the store code in the file name
# --------------------------------------------------------------------------

_SEPARATORS = "_- .("


def _match_store(stem: str, index: dict[str, list[Store]]) -> tuple[Store | None, str | None]:
    """(store, problem). Longest store code that equals the file stem or prefixes it before a separator."""
    low = stem.strip().lower()
    best: str | None = None
    for code in index:
        if low == code or (low.startswith(code) and len(low) > len(code) and low[len(code)] in _SEPARATORS):
            if best is None or len(code) > len(best):
                best = code
    if best is None:
        return None, "no store code found in the file name"
    stores = index[best]
    if len(stores) > 1:
        return None, f"store code '{best}' exists on more than one platform"
    return stores[0], None


def bulk_upload(
    db: Session, user: User, perms: set[str], month_str: str, kind: str, files: list[tuple[str, bytes]],
) -> BulkUploadResult:
    if kind not in VALID_KINDS:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"kind must be one of: {', '.join(VALID_KINDS)}.")
    if not files:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one file.")
    if len(files) > MAX_BULK_FILES:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Upload at most {MAX_BULK_FILES} files at once.")
    month = parse_month(month_str)

    index: dict[str, list[Store]] = {}
    for s in _accessible_stores(db, user, perms, live_only=False):
        index.setdefault(s.external_code.strip().lower(), []).append(s)

    grouped: dict[uuid.UUID, tuple[Store, list[tuple[str, bytes]]]] = {}
    unmatched: list[str] = []
    for name, data in files:
        stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        store, problem = _match_store(stem, index)
        if store is None:
            unmatched.append(f"{name} — {problem}")
            continue
        grouped.setdefault(store.id, (store, []))[1].append((name, data))

    failed: list[BulkFailure] = []
    updated = 0
    matched = 0
    def natural(name: str) -> list:
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name.lower())]

    for store, blobs in grouped.values():
        blobs.sort(key=lambda b: natural(b[0]))  # page order = file-name order ("page 2" before "page 10")
        try:
            data, ext = _prepare(blobs)  # same rules as a normal upload: 1 file as-is, 2+ photos -> one PDF, PDF alone
        except HTTPException as exc:
            failed.append(BulkFailure(store=f"{store.name} ({store.external_code})", error=str(exc.detail)))
            continue
        _save_document(db, user, store, month, kind, data, ext, len(blobs))
        updated += 1
        matched += len(blobs)

    activity_service.record(
        db, actor=user, action="compliance.bulk_uploaded", entity_type="compliance_document", entity_id=user.id,
        metadata={"kind": kind, "month": f"{month:%Y-%m}", "stores": updated, "unmatched": len(unmatched)},
    )
    db.commit()
    return BulkUploadResult(
        kind=kind, month=f"{month:%Y-%m}", files_received=len(files), files_matched=matched, stores_updated=updated,
        unmatched=unmatched[:50], failed=failed[:50],
    )


def _save_document(db: Session, user: User, store: Store, month: date, kind: str, data: bytes, ext: str, n_files: int) -> None:
    """Add the next version of the (store, month, kind) document (no commit). Earlier files are kept."""
    if store.partner_organization is None:
        db.refresh(store)
    save_document(db, user, store, month, kind, data, ext, n_files)


# --------------------------------------------------------------------------
# summary PDF for the selected stores
# --------------------------------------------------------------------------

_KIND_TITLE = {DocKind.CARD.value: "Compliance card", DocKind.BILL.value: "Invoice", DocKind.PAYMENT.value: "Payment proof"}
_HEADER_BAND = 34.0  # points added above every page for the outlet id / store name


def summary_pdf(db: Session, user: User, perms: set[str], store_ids: list[uuid.UUID], month_str: str | None) -> bytes:
    """One collective PDF: for every selected store (by name), its card, invoice and payment proof for the month -
    photos and PDFs alike - each page topped with a band showing the outlet id and the store name. The original
    page is placed unchanged below the band, so nothing on it is covered."""
    import pymupdf

    month = parse_month(month_str)
    wanted = set(store_ids)
    stores = [s for s in _accessible_stores(db, user, perms, live_only=False) if s.id in wanted]
    if not stores:
        raise _err(status.HTTP_404_NOT_FOUND, "None of those stores were found.")
    docs = _docs(db, [s.id for s in stores], month)

    out = pymupdf.open()
    stores_with_files = 0
    for s in sorted(stores, key=lambda s: s.name.lower()):
        pages_before = out.page_count
        for kind in REQUIRED:
            d = docs.get(s.id, {}).get(kind)
            if d is None or not storage.exists(d.file_key):
                continue
            raw = storage.read(d.file_key)
            try:
                src = pymupdf.open(stream=raw, filetype="pdf" if d.content_type == "application/pdf" else d.file_key.rsplit(".", 1)[-1])
                if not src.is_pdf:  # a photo: turn it into a one-page PDF first
                    src = pymupdf.open("pdf", src.convert_to_pdf())
            except Exception:  # a damaged file must not sink the whole export
                continue
            for pno in range(src.page_count):
                box = src[pno].rect
                page = out.new_page(width=box.width, height=box.height + _HEADER_BAND)
                page.show_pdf_page(pymupdf.Rect(0, _HEADER_BAND, box.width, box.height + _HEADER_BAND), src, pno)
                page.draw_rect(pymupdf.Rect(0, 0, box.width, _HEADER_BAND), color=None, fill=(0.145, 0.349, 0.788))
                head = f"Outlet ID: {s.external_code}   |   {s.name}"
                tag = f"{_KIND_TITLE[kind]} - {month_label(month)}"
                room = box.width - 24
                tag_w = pymupdf.get_text_length(tag, fontname="helv", fontsize=9)
                show_tag = box.width >= 480  # small pages (thumbnails): the id and name get the whole band
                head_room = room - (tag_w + 16 if show_tag else 0)
                size = max(5.0, min(12.0, 12.0 * head_room / max(pymupdf.get_text_length(head, fontname="hebo", fontsize=12), 1)))
                page.insert_text((12, 22), head, fontsize=size, fontname="hebo", color=(1, 1, 1))
                if show_tag:
                    page.insert_text((box.width - 12 - tag_w, 22), tag, fontsize=9, fontname="helv", color=(1, 1, 1))
            src.close()
        stores_with_files += out.page_count > pages_before
    if out.page_count == 0:
        raise _err(status.HTTP_404_NOT_FOUND, "None of the selected stores has a file uploaded for this month.")
    out.set_metadata({"title": f"Store compliance - {month_label(month)}", "author": settings.COMPANY_NAME})
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data
