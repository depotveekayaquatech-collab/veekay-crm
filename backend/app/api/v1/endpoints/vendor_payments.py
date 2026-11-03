"""
Vendor Payments tab. Everyone on staff may READ (vendorpay.view); there is no write endpoint on that side at all.
Everything under /admin needs vendorpay.manage (administrators and the developer): CSV upload, vendors, unmatched codes, sync history, API-key help.
"""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_page_params, require_permission
from app.core.config import settings
from app.core.roles import VENDORPAY_MANAGE, VENDORPAY_VIEW
from app.db.session import get_db
from app.models.busy_ledger import SOURCE_CSV
from app.models.user import User
from app.schemas.busy_ledger import (
    AdminVendorOut, CodeCheck, CsvPreview, Freshness, GeneratedKey, KeyInfo, ResolveResult, SummaryPage, SyncLogOut, UnmatchedCreateVendor,
    UnmatchedGroup, UnmatchedMap, VendorChoice, VendorCreate, VendorDetail, VendorUpdate,
)
from app.schemas.common import Page, PageParams
from app.services import busy_admin_service as admin, busy_csv_service as csv_import, busy_ledger_service as ledger
from app.services.busy_sync_service import MODE_UPSERT, run_sync

router = APIRouter(prefix="/vendor-payments", tags=["vendor-payments"])

MONTH = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM; the current month (India time) when left out")
view = Depends(require_permission(VENDORPAY_VIEW))
manage = Depends(require_permission(VENDORPAY_MANAGE))


# ---- read-only, for every staff member ------------------------------------------------------

@router.get("/status", response_model=Freshness, dependencies=[view])
def sync_status(db: Session = Depends(get_db)) -> Freshness:
    """When the data was last brought in by a successful sync, and whether that is older than BUSY_STALE_HOURS."""
    return ledger.freshness(db)


@router.get("/vendors", response_model=list[VendorChoice], dependencies=[view])
def search_vendors(q: str = Query("", max_length=100), limit: int = Query(20, ge=1, le=1000), db: Session = Depends(get_db)) -> list[VendorChoice]:
    """The vendor dropdown: searches name, city and vendor code. The web page asks for up to 1000 and filters as you type."""
    return ledger.search_vendors(db, q, limit)


@router.get("/summary", response_model=SummaryPage, dependencies=[view])
def summary(
    month: str | None = MONTH,
    sort: Literal["name", "city", "code", "month_total", "paid", "pending", "closing"] = "name",
    direction: Literal["asc", "desc"] = "asc",
    params: PageParams = Depends(get_page_params),
    db: Session = Depends(get_db),
) -> SummaryPage:
    """'All vendors': one row per active vendor for the month, sorted and paged, with the totals of ALL vendors (not just this page)."""
    return ledger.summary(db, month or ledger.current_month(), sort=sort, descending=direction == "desc", page=params.page, page_size=params.page_size)


@router.get("/vendors/{vendor_code}", response_model=VendorDetail)
def vendor_detail(
    vendor_code: str,
    month: str | None = MONTH,
    months: int = Query(ledger.DEFAULT_HISTORY_MONTHS, ge=1, le=ledger.MAX_HISTORY_MONTHS),
    _: User = view,
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> VendorDetail:
    """One vendor: the month's four figures, the month-by-month history ending at that month, and the month's ledger entries."""
    vendor = admin.get_vendor(db, vendor_code)
    if not vendor.is_active and VENDORPAY_MANAGE not in perms:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No vendor has that code.")
    return ledger.vendor_detail(db, vendor, month or ledger.current_month(), months)


# ---- admin ------------------------------------------------------------------------------------

@router.get("/admin/vendors", response_model=Page[AdminVendorOut], dependencies=[manage])
def admin_vendors(q: str = Query("", max_length=100), active: bool | None = None, params: PageParams = Depends(get_page_params), db: Session = Depends(get_db)):
    return admin.list_vendors(db, params, q, active)


@router.get("/admin/vendors/check-code", response_model=CodeCheck, dependencies=[manage])
def admin_check_code(code: str = Query(..., max_length=64), db: Session = Depends(get_db)) -> CodeCheck:
    """Duplicate-code check for the add-vendor form."""
    return admin.check_code(db, code)


@router.post("/admin/vendors", response_model=AdminVendorOut, status_code=status.HTTP_201_CREATED)
def admin_create_vendor(body: VendorCreate, user: User = manage, db: Session = Depends(get_db)):
    vendor = admin.create_vendor(db, user, body)
    db.commit()
    return vendor


@router.patch("/admin/vendors/{vendor_code}", response_model=AdminVendorOut)
def admin_update_vendor(vendor_code: str, body: VendorUpdate, user: User = manage, db: Session = Depends(get_db)):
    """Name, city, opening balance / date and the active flag. The code itself can never be changed (the body refuses it)."""
    vendor = admin.update_vendor(db, user, vendor_code, body)
    db.commit()
    return vendor


@router.get("/admin/sync-logs", response_model=Page[SyncLogOut], dependencies=[manage])
def admin_sync_logs(params: PageParams = Depends(get_page_params), db: Session = Depends(get_db)):
    return admin.list_sync_logs(db, params)


@router.get("/admin/unmatched", response_model=list[UnmatchedGroup], dependencies=[manage])
def admin_unmatched(db: Session = Depends(get_db)) -> list[UnmatchedGroup]:
    """Valid rows whose vendor_code is not a CRM vendor, grouped by code. Nothing is dropped; resolve each group below."""
    return admin.unmatched_groups(db)


@router.post("/admin/unmatched/create-vendor", response_model=ResolveResult)
def admin_unmatched_create(body: UnmatchedCreateVendor, user: User = manage, db: Session = Depends(get_db)) -> ResolveResult:
    result = admin.resolve_by_creating_vendor(db, user, body)
    db.commit()
    return result


@router.post("/admin/unmatched/map", response_model=ResolveResult)
def admin_unmatched_map(body: UnmatchedMap, user: User = manage, db: Session = Depends(get_db)) -> ResolveResult:
    result = admin.resolve_by_mapping(db, user, body)
    db.commit()
    return result


@router.get("/admin/key-info", response_model=KeyInfo, dependencies=[manage])
def admin_key_info() -> KeyInfo:
    return admin.key_info()


@router.post("/admin/key-info/generate", response_model=GeneratedKey, dependencies=[manage])
def admin_generate_key() -> GeneratedKey:
    """A fresh random key to copy. It is NOT saved or activated: set it as BUSY_SYNC_API_KEY on the server yourself."""
    return admin.generate_key()


@router.get("/admin/csv/template", dependencies=[manage])
def admin_csv_template() -> Response:
    return Response(content=csv_import.template_csv(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="vendor-payments-template.csv"'})


def _read_upload(file: UploadFile, mapping: str):
    headers, body = csv_import.read_csv(file.file.read(settings.BUSY_CSV_MAX_MB * 1024 * 1024 + 1))
    return headers, body, csv_import.parse_mapping(mapping, headers)


@router.post("/admin/csv/preview", response_model=CsvPreview, dependencies=[manage])
def admin_csv_preview(file: UploadFile = File(...), mapping: str = Form(""), db: Session = Depends(get_db)) -> CsvPreview:
    """Dry run: reads the file with the column mapping and reports what an import would insert, update, leave alone, park as unmatched and reject. Changes nothing."""
    headers, body, chosen = _read_upload(file, mapping)
    outcome = None
    if not csv_import.missing_fields(chosen):
        outcome = run_sync(db, entries=csv_import.to_entries(headers, body, chosen), mode=MODE_UPSERT, source=SOURCE_CSV, triggered_by=None, dry_run=True)
    return csv_import.preview(headers, body, chosen, outcome)


@router.post("/admin/csv/import")
def admin_csv_import(file: UploadFile = File(...), mapping: str = Form(""), user: User = manage, db: Session = Depends(get_db)) -> dict:
    """Does the import for real (valid rows are saved, rejected rows are listed) and writes a sync-history entry."""
    headers, body, chosen = _read_upload(file, mapping)
    missing = csv_import.missing_fields(chosen)
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Map these columns first: " + ", ".join(missing))
    outcome = run_sync(db, entries=csv_import.to_entries(headers, body, chosen), mode=MODE_UPSERT, source=SOURCE_CSV, triggered_by=f"{user.full_name} ({user.employee_code})")
    return outcome.to_dict()

