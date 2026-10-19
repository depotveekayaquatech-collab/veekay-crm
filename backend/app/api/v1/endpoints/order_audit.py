"""Order entry audit (developer): the log of what employees submitted against what is stored and visible, and the repair for lost entries."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import order_audit_service

router = APIRouter(prefix="/developer/order-audit", tags=["developer"], dependencies=[Depends(require_permission("sheets.sync"))])


class RestoreIn(BaseModel):
    start: date
    end: date
    dry_run: bool = True


@router.get("")
def run_audit(
    start: date = Query(...), end: date = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """For each entry employees logged in the window: fine, changed, cleared, missing (and why), or hidden because its store is no longer live."""
    return order_audit_service.audit(db, user, start, end)


@router.post("/restore")
def restore(body: RestoreIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Re-create the entries the log shows but the database lacks. dry_run (the default) only counts them."""
    return order_audit_service.restore(db, user, body.start, body.end, dry_run=body.dry_run)
