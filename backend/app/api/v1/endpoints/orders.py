"""Order-entry (bottle-count) routes."""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

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
from app.services import inventory_service, order_import_service, order_service, report_service

router = APIRouter(prefix="/orders", tags=["orders"])

ADMIN_VIEW = "orders.correct"  # anyone who can correct sees any store


def _is_admin(perms: set[str]) -> bool:
    return ADMIN_VIEW in perms


@router.get(
    "/my-stores", response_model=list[MyStore],
    dependencies=[Depends(require_permission("orders.mark"))],
)
def my_stores(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MyStore]:
    return order_service.my_stores(db, user)


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderCalendar:
    return order_service.mark(db, user, payload)


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
    return order_service.dashboard_insights(db, user)


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
    return order_service.daily_overview(db, user, partner, day_offset)


@router.get(
    "/report", response_model=SalesReport,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def report(
    start: date | None = None,
    end: date | None = None,
    group_by: str = "region",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesReport:
    end = end or date.today()
    start = start or end - timedelta(days=29)
    return report_service.sales_report(db, user, start, end, group_by)


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
    dependencies=[Depends(require_permission("orders.correct"))],
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


@router.get(
    "/inventory", response_model=Inventory,
    dependencies=[Depends(require_permission("orders.view"))],
)
def inventory(
    partner: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Inventory:
    """Stores with vendor/POC details and pending days. Employees get their own
    stores; admins (orders.correct) get every live store, optionally per platform."""
    return inventory_service.inventory(db, user, is_admin=_is_admin(perms), partner_slug=partner)
