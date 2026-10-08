"""Order-entry (bottle-count) routes."""
import uuid
from datetime import date, timedelta

from pydantic import TypeAdapter
from fastapi import APIRouter, Depends, Query, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.cache import read_cache
from app.core.cached_json import cached_json_response
from app.core.config import settings
from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.order import (
    AdminEntryRequest,
    DailyOverview,
    DashboardInsights,
    MarkRequest,
    MyStore,
    OrderCalendar,
    OrderImportResult,
)
from app.schemas.inventory import Inventory
from app.schemas.report import PendingEntries, SalesReport
from app.services import inventory_service, matrix_service, order_import_service, order_service, report_service

router = APIRouter(prefix="/orders", tags=["orders"])

_MY_STORES = TypeAdapter(list[MyStore])
_INVENTORY = TypeAdapter(Inventory)
_REPORT = TypeAdapter(SalesReport)

ADMIN_VIEW = "orders.correct"  # anyone who can correct sees any store


def _is_admin(perms: set[str]) -> bool:
    return ADMIN_VIEW in perms


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
    return order_service.get_calendar(
        db, user, store_id, year or today.year, month or today.month, is_admin=_is_admin(perms)
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
) -> OrderCalendar:
    return order_service.mark(db, user, payload, is_admin=_is_admin(perms))


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardInsights:
    # Organisation-wide numbers: computed once per few seconds and shared (single-flight), dropped on any write.
    return read_cache.get_or_set(
        ("insights", user.organization_id), settings.DASHBOARD_CACHE_SECONDS,
        lambda: order_service.dashboard_insights(db, user),
    ) if settings.DASHBOARD_CACHE_SECONDS else order_service.dashboard_insights(db, user)


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
        result = order_import_service.import_orders(
            db, user, platform, file.filename or "", content, overwrite=overwrite
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
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Daily distribution: one row per store, one column per day (max 62 days)."""
    return matrix_service.matrix(
        db, user, start, end, partner=partner, state=state, city=city,
        page=max(1, page), page_size=min(max(1, page_size), 200),
    )


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    data = matrix_service.matrix_xlsx(db, user, start, end, partner=partner, state=state, city=city)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="daily-distribution-{start}_{end}.xlsx"'},
    )
