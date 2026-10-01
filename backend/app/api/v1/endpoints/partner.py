"""Partner-account home: an overview of the caller's own platform."""
from fastapi import APIRouter, Depends
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
