"""Order-entry (bottle-count) routes."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends
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
)
from app.services import order_service

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
