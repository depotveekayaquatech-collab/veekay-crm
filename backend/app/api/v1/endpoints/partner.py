"""Partner-account home: an overview of the caller's own platform."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import partner_service

router = APIRouter(prefix="/partner", tags=["partner"])


@router.get("/overview")
def overview(
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Stores, today's entries, bottles, regions and tickets — for the platform this partner account belongs to."""
    return partner_service.overview(db, user, perms)


@router.get("/delivery-report")
def delivery_report(
    start: date | None = None,
    end: date | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Download-only delivery report: one row per store of the caller's platform, one column per day. No totals."""
    if "reports.delivery" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to access this.")
    end = end or date.today()
    start = start or end - timedelta(days=6)
    data, name = partner_service.delivery_report_xlsx(db, user, start, end)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )
