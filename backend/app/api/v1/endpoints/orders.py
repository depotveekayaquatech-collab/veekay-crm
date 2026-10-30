"""Order-entry (bottle-count) routes."""
import uuid
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, TypeAdapter
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, Header, Query, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.cache import read_cache
from app.core.cached_json import cached_json_response
from app.core import entry_access
from app.core.config import settings
from app.core.idempotency import idempotency_key_header
from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.order import (
    AdminEntryRequest,
    DailyOverview,
    DashboardInsights,
    MarkManyRequest,
    MarkManyResult,
    MarkRequest,
    MyStore,
    OrderCalendar,
    OrderImportResult,
)
from app.schemas.inventory import Inventory
from app.schemas.report import PendingEntries, SalesReport
from app.services import inventory_service, matrix_service, order_import_service, order_revert_service, order_service, report_service

router = APIRouter(prefix="/orders", tags=["orders"])

_MY_STORES = TypeAdapter(list[MyStore])
_INVENTORY = TypeAdapter(Inventory)
_REPORT = TypeAdapter(SalesReport)

ADMIN_VIEW = "orders.correct"  # anyone who can correct sees any store


def _is_admin(perms: set[str]) -> bool:
    return ADMIN_VIEW in perms


def _client_time(value: str | None) -> str | None:
    """The phone's own clock, kept only for diagnosis (never authoritative). Anything that is not a timestamp is dropped."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


@router.get(
    "/my-stores", response_model=list[MyStore],
    dependencies=[Depends(require_permission("orders.view"))],
)
def my_stores(
    request: Request,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MyStore]:
    if _is_admin(perms):
        # The same list for every admin of the organisation: built, serialised and gzipped once, then shared.
        return cached_json_response(
            request, ("my-stores-admin", user.organization_id),
            lambda: _MY_STORES.dump_json(order_service.my_stores(db, user, is_admin=True)),
        )
    return order_service.my_stores(db, user, is_admin=_is_admin(perms))


@router.get("/my-entries", dependencies=[Depends(require_permission("orders.view"))])
def my_entries(
    days: int = Query(7, ge=1, le=14), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Everything the caller entered in the last few days, including stores that are no longer live, so no entry seems to have vanished."""
    from app.services import order_audit_service

    return order_audit_service.my_entries(db, user, days)


@router.get(
    "/calendar", response_model=OrderCalendar,
    dependencies=[Depends(require_permission("orders.view"))],
)
def calendar(
    store_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderCalendar:
    today = date.today()
    admin = _is_admin(perms)
    return order_service.get_calendar(
        db, user, store_id, year or today.year, month or today.month, is_admin=admin,
        scope=None if admin else entry_access.scope_for(db, user, perms),
    )


@router.post(
    "/mark", response_model=OrderCalendar,
    dependencies=[Depends(require_permission("orders.mark"))],
)
def mark(
    payload: MarkRequest,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idem: str | None = Depends(idempotency_key_header),
    client_time: str | None = Header(default=None, alias="X-Client-Time", max_length=40),
) -> OrderCalendar:
    """Send the same `Idempotency-Key` when you retry: a lost response then never creates a second entry or a false "already marked"."""
    return order_service.mark(db, user, payload, is_admin=_is_admin(perms), request_key=idem, client_time=_client_time(client_time))


@router.post(
    "/mark-many", response_model=MarkManyResult,
    dependencies=[Depends(require_permission("orders.mark"))],
)
def mark_many(
    payload: MarkManyRequest,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idem: str | None = Depends(idempotency_key_header),
    client_time: str | None = Header(default=None, alias="X-Client-Time", max_length=40),
) -> MarkManyResult:
    """Several dates of one store with a count each, in one request. Each date is checked on its own (see the per-date results).
    A saved date comes back with its entry id, version and server time: that is the server's confirmation."""
    return order_service.mark_many(db, user, payload, is_admin=_is_admin(perms), request_key=idem, client_time=_client_time(client_time))


class RevertImportRequest(BaseModel):
    platform: str
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    run_ids: list[uuid.UUID]
    dry_run: bool = True
    confirm: str = ""


@router.get("/import-runs", dependencies=[Depends(require_permission("sheets.sync"))])
def import_runs(
    platform: str, month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Developer only. The order imports of a platform that left entries in a month, with how much each one can undo."""
    return order_revert_service.import_runs(db, user, platform, month)


@router.post("/import-revert", dependencies=[Depends(require_permission("sheets.sync"))])
def import_revert(payload: RevertImportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Developer only. Put ONE month back the way it was before the chosen imports: entries they created are deleted (kept in deleted_rows),
    numbers they overwrote are restored. `dry_run` (default) only counts; applying needs confirm = `REVERT <PLATFORM> <YYYY-MM>`."""
    if not payload.dry_run:
        expected = f"REVERT {payload.platform.strip().upper()} {payload.month}"
        if payload.confirm.strip().upper() != expected:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f'Type "{expected}" to confirm.')
    result = order_revert_service.revert(db, user, payload.platform, payload.month, payload.run_ids, dry_run=payload.dry_run)
    if not payload.dry_run:
        read_cache.invalidate()
    return result


@router.patch(
    "/my-entry", response_model=OrderCalendar,
    dependencies=[Depends(require_permission("orders.mark"))],
)
def correct_my_entry(
    payload: AdminEntryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderCalendar:
    """A Level 1 employee corrects (or clears, with no count) ANY entry of their stores in the dates they can still mark, whoever entered it. Always audited."""
    result = order_service.correct_own_entry(db, user, payload)
    read_cache.invalidate()
    return result


@router.patch(
    "/entry", response_model=OrderCalendar,
    dependencies=[Depends(require_permission("orders.correct"))],
)
def correct_entry(
    payload: AdminEntryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderCalendar:
    return order_service.admin_set_entry(db, user, payload)


@router.get(
    "/insights", response_model=DashboardInsights,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def insights(
    partner: str | None = Query(None, max_length=32, description="Platform (blinkit / zepto): everything is then for that platform only"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardInsights:
    # Computed once per few seconds per platform and shared (single-flight), dropped on any write.
    key = (partner or "").strip().lower() or None
    return read_cache.get_or_set(
        ("insights", user.organization_id, key), settings.DASHBOARD_CACHE_SECONDS,
        lambda: order_service.dashboard_insights(db, user, partner_slug=key),
    ) if settings.DASHBOARD_CACHE_SECONDS else order_service.dashboard_insights(db, user, partner_slug=key)


@router.get(
    "/daily-overview", response_model=DailyOverview,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def daily_overview(
    partner: str,
    day_offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyOverview:
    compute = lambda: order_service.daily_overview(db, user, partner, day_offset)  # noqa: E731
    if not settings.DASHBOARD_CACHE_SECONDS:
        return compute()
    return read_cache.get_or_set(("overview", user.organization_id, partner, 1 if day_offset == 1 else 0), settings.DASHBOARD_CACHE_SECONDS, compute)


@router.get("/performance", dependencies=[Depends(require_permission("orders.view"))])
def performance(
    response: Response, partner: str, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Each employee's share of the entries they should have marked this month, counted from the 1st to yesterday, recounted on every call (so entries
    marked late lift the earlier days). Never cached. An administrator, a reviewer or anyone with the daily overview sees everyone; a Team Lead sees their
    own team only; every other employee sees only themselves."""
    from app.services import assignment_service, performance_service

    if assignment_service.is_partner_account(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Performance is for Veekay staff.")
    response.headers["Cache-Control"] = "no-store"
    today = performance_service.business_today()                  # the IST date: the report rolls over at midnight IST, not at 05:30
    return performance_service.performance(db, user, partner.strip().lower(), performance_service.parse_month(month, today), today, perms)


@router.get("/performance/pending", dependencies=[Depends(require_permission("orders.view"))])
def performance_pending(
    response: Response, partner: str, day: date = Query(..., alias="date"), employee_id: uuid.UUID | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """The stores of one employee (default: the caller) with days still to mark from the 1st of the month up to `date`, each with its missing dates: what
    brings the percentage to 100 as of that date. Only yourself, or your team for a Team Lead, unless you see everyone. Never cached."""
    from app.services import assignment_service, performance_service

    if assignment_service.is_partner_account(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Performance is for Veekay staff.")
    response.headers["Cache-Control"] = "no-store"
    return performance_service.pending_stores(
        db, user, perms, partner.strip().lower(), employee_id, day, performance_service.business_today(), is_admin=_is_admin(perms))


@router.get("/performance/vendors", dependencies=[Depends(require_permission("orders.view"))])
def performance_vendors(
    response: Response, partner: str, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Vendor-wise: each vendor's stores with the bottles marked at each one this month (1st to today). A vendor with one store has one row. Never cached.
    An administrator or anyone with the daily overview sees the whole platform; an employee or Team Lead sees the vendors of their own stores only.
    Platform logins (a Blinkit or Zepto account) are not shown another company's vendors."""
    from app.services import assignment_service, performance_service

    if assignment_service.is_partner_account(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vendor performance is for Veekay staff.")
    response.headers["Cache-Control"] = "no-store"
    today = performance_service.business_today()
    full = _is_admin(perms) or "orders.overview" in perms
    return performance_service.vendors(db, user, partner.strip().lower(), performance_service.parse_month(month, today), today, full=full)


# ---- performance: stored reports and reconciliation (administrators and entry reviewers only; the permission is checked in the service, from this request) ----

class SnapshotRequest(BaseModel):
    partner: str = Field(max_length=32)
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    source: str = Field("manual", pattern="^(manual|report)$")          # 'scheduled' is written by the daily job only
    report_text: str | None = Field(None, max_length=60_000)             # the literal text that was copied, so what was sent is on record
    revision_of: uuid.UUID | None = None
    revision_reason: str | None = Field(None, max_length=1000)


def _reconciler(user: User, perms: set[str], db: Session, partner_slug: str):
    from app.services import assignment_service, performance_reconciliation_service as rec, performance_service

    if assignment_service.is_partner_account(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Performance is for Veekay staff.")
    partner = performance_service._partner(db, partner_slug.strip().lower())
    rec.require_reviewer(db, user, perms, partner)
    return rec, partner


@router.post("/performance/snapshots", dependencies=[Depends(require_permission("orders.view"))])
def performance_snapshot_create(
    payload: SnapshotRequest, response: Response,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Keep what the performance report says right now (the figures, the judged days, the stores behind each employee, the instant of the data).
    Never edited afterwards: a correction is a new snapshot that names the one it revises and says why."""
    from app.services import performance_service

    rec, partner = _reconciler(user, perms, db, payload.partner)
    response.headers["Cache-Control"] = "no-store"
    month = performance_service.parse_month(payload.month, performance_service.business_today())
    snap = rec.create_snapshot(user.id, partner.slug, month, source=payload.source, report_text=payload.report_text,
                               revision_of=payload.revision_of, revision_reason=payload.revision_reason)
    return rec.snapshot_row(snap)


@router.get("/performance/snapshots", dependencies=[Depends(require_permission("orders.view"))])
def performance_snapshot_list(
    response: Response, partner: str, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    from app.services import performance_service

    rec, p = _reconciler(user, perms, db, partner)
    response.headers["Cache-Control"] = "no-store"
    m = performance_service.parse_month(month, performance_service.business_today())
    return {"partner_slug": p.slug, "month": f"{m:%Y-%m}", "snapshots": rec.list_snapshots(db, user.organization_id, p.slug, m)}


@router.get("/performance/snapshots/{snapshot_id}", dependencies=[Depends(require_permission("orders.view"))])
def performance_snapshot_detail(
    snapshot_id: uuid.UUID, response: Response, partner: str,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """One stored report, rebuilt from the records at its instant and compared with what it stored (`reproduced`)."""
    rec, _ = _reconciler(user, perms, db, partner)
    response.headers["Cache-Control"] = "no-store"
    return rec.verify_snapshot(db, user.organization_id, snapshot_id)


@router.get("/performance/reconciliation", dependencies=[Depends(require_permission("orders.view"))])
def performance_reconciliation(
    response: Response, partner: str, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    previous_snapshot: uuid.UUID | None = None, current_snapshot: uuid.UUID | None = None,
    previous_at: datetime | None = None, current_at: datetime | None = None, employee_id: uuid.UUID | None = None,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Why did each employee's figure change between two reports? Each side is a stored snapshot (`*_snapshot`), an instant rebuilt from the records (`*_at`),
    or, for `current`, right now. With no `previous`, the latest snapshot before `current`, else the day before. Every difference is split into named causes
    (a new day, entries added, entries cleared with who and when, stores changing hands); whatever the records cannot explain is listed as
    unexplained and the employee (and the report) is marked for review."""
    from app.services import performance_service

    rec, p = _reconciler(user, perms, db, partner)
    response.headers["Cache-Control"] = "no-store"
    m = performance_service.parse_month(month, performance_service.business_today())
    if (previous_snapshot and previous_at) or (current_snapshot and current_at):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a snapshot or a time for each side, not both.")
    for t in (previous_at, current_at):
        if t is not None and t.tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Times need a time zone, for example 2026-10-29T10:37:00+05:30.")
    curr = rec.point_for(db, user.organization_id, p, m, snapshot_id=current_snapshot, at=current_at)
    if previous_snapshot or previous_at:
        prev = rec.point_for(db, user.organization_id, p, m, snapshot_id=previous_snapshot, at=previous_at)
    else:
        earlier = [s for s in rec.list_snapshots(db, user.organization_id, p.slug, m) if s["generated_at"] < curr.state.cutoff and s["id"] != current_snapshot]
        prev = (rec.point_for(db, user.organization_id, p, m, snapshot_id=earlier[0]["id"]) if earlier
                else rec.point_for(db, user.organization_id, p, m, at=curr.state.cutoff - timedelta(days=1)))
    return rec.compare(db, user.organization_id, p, m, prev, curr, employee_id)


@router.get(
    "/report", response_model=SalesReport,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def report(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    group_by: str = "region",
    partner: str | None = None,
    region: str | None = None,
    state: str | None = None,
    limit: int | None = Query(None, ge=1, le=500, description="Keep only the top N breakdown rows (totals and the daily series stay complete)."),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesReport:
    """Bottle totals for a date range. `partner` (platform slug), `region` (name) and `state` narrow it."""
    end = end or date.today()
    start = start or end - timedelta(days=29)
    def build() -> SalesReport:
        rep = report_service.sales_report(
            db, user, start, end, group_by,
            partner_slug=(partner or "").strip().lower() or None, region=(region or "").strip() or None, state=(state or "").strip() or None,
        )
        return rep.model_copy(update={"rows": rep.rows[:limit]}) if limit else rep

    return cached_json_response(
        request, ("report", user.organization_id, start, end, group_by, partner, region, state, limit),
        lambda: _REPORT.dump_json(build()),
    )


@router.get(
    "/pending", response_model=PendingEntries,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def pending(
    day_offset: int = 0,
    partner: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PendingEntries:
    return report_service.pending_entries(db, user, day_offset, partner)


@router.post(
    "/import", response_model=OrderImportResult,
    dependencies=[Depends(require_permission("sheets.sync"))],
)
async def import_orders(
    platform: str = Form(...),
    overwrite: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderImportResult:
    """Bulk-mark orders from an order sheet (one row per store, one column per date)."""
    content = await file.read(order_import_service.MAX_UPLOAD_BYTES + 1)
    try:
        # Blocking parse + database work: a worker thread, so every other request keeps being served meanwhile.
        result = await run_in_threadpool(
            order_import_service.import_orders, db, user, platform, file.filename or "", content, overwrite=overwrite
        )
    except order_import_service.OrderImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DBAPIError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The database rejected a value in this file. Check for malformed cells.",
        ) from exc
    return OrderImportResult(**result.as_dict())


@router.post(
    "/sync", response_model=list[OrderImportResult],
    dependencies=[Depends(require_permission("sheets.sync"))],
)
def sync_orders(
    platform: str | None = None,
    overwrite: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OrderImportResult]:
    """Pull order counts from the configured Google Sheet(s). `platform` limits it to one;
    omitted syncs every configured sheet. `overwrite` defaults to ORDER_SYNC_OVERWRITE."""
    try:
        if platform:
            results = [order_import_service.sync_platform(db, user, platform, overwrite=overwrite)]
        else:
            if not settings.order_sheet_sources():
                raise order_import_service.OrderImportError(
                    "No order sheets are configured. Set ORDER_SYNC_SHEETS on the server first."
                )
            results = order_import_service.sync_all(db, user, overwrite=overwrite)
    except order_import_service.OrderImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DBAPIError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The database rejected a value in the sheet. Check for malformed cells.",
        ) from exc
    return [OrderImportResult(**r.as_dict()) for r in results]


@router.get(
    "/inventory", response_model=Inventory,
    dependencies=[Depends(require_permission("orders.view"))],
)
def inventory(
    request: Request,
    partner: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Inventory:
    """Stores with vendor/POC details and pending days. Employees get their own
    stores; admins (orders.correct) get every live store, optionally per platform."""
    if _is_admin(perms):
        return cached_json_response(
            request, ("inventory-admin", user.organization_id, partner or ""),
            lambda: _INVENTORY.dump_json(inventory_service.inventory(db, user, is_admin=True, partner_slug=partner)),
        )
    return inventory_service.inventory(db, user, is_admin=_is_admin(perms), partner_slug=partner)


@router.get(
    "/matrix",
    dependencies=[Depends(require_permission("orders.overview"))],
)
def matrix(
    start: date,
    end: date,
    partner: str | None = None,
    state: str | None = None,
    city: str | None = None,
    region: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Daily distribution: one row per store, one column per day (max 62 days)."""
    return matrix_service.matrix(
        db, user, start, end, partner=partner, state=state, city=city, region=region,
        page=max(1, page), page_size=min(max(1, page_size), 200),
    )


@router.get("/matrix/regions", dependencies=[Depends(require_permission("orders.overview"))])
def matrix_regions(partner: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """The regions to offer in the matrix's Region filter: those that have stores of the chosen channel."""
    return matrix_service.regions_for(db, user, partner)


@router.get(
    "/matrix/export",
    dependencies=[Depends(require_permission("orders.overview"))],
)
def matrix_export(
    start: date,
    end: date,
    partner: str | None = None,
    state: str | None = None,
    city: str | None = None,
    region: uuid.UUID | None = None,
    include_rate: bool = False,
    blank_as_zero: bool = True,
    user: User = Depends(get_current_user),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> Response:
    """`blank_as_zero` (default true): a day nobody marked is 0 in the file; false leaves it an empty cell."""
    if include_rate and "rates.manage" not in perms:   # the vendor-rate columns are for admins only
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to the vendor rate report.")
    data = matrix_service.matrix_xlsx(db, user, start, end, partner=partner, state=state, city=city, region=region, with_rates=include_rate, blank_as_zero=blank_as_zero)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="daily-distribution{"-with-rate" if include_rate else ""}-{start}_{end}.xlsx"'},
    )
