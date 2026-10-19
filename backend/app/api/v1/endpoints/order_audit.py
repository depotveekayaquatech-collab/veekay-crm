"""Order entry audit (developer): the log of what employees submitted against what is stored and visible, and the repair for lost entries."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import deleted_data_service, order_audit_service

router = APIRouter(prefix="/developer/order-audit", tags=["developer"], dependencies=[Depends(require_permission("sheets.sync"))])


class RestoreIn(BaseModel):
    start: date
    end: date
    dry_run: bool = True


class RestoreDeletedIn(BaseModel):
    ids: list[uuid.UUID] | None = None
    start: date | None = None
    end: date | None = None
    dry_run: bool = True


@router.get("/deleted")
def deleted_entries(
    start: date | None = Query(None), end: date | None = Query(None), include_restored: bool = Query(False),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Order entries that were deleted (by an admin clearing a day, a store removal, a developer tool or SQL), as the database kept them, and whether each can be put back."""
    return deleted_data_service.list_deleted(db, user, start, end, include_restored=include_restored)


@router.post("/deleted/restore")
def restore_deleted(body: RestoreDeletedIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Put deleted entries back: the chosen ones (ids) or every one in a date range. Never over an entry that exists. dry_run (the default) only counts."""
    return deleted_data_service.restore(db, user, ids=body.ids, start=body.start, end=body.end, dry_run=body.dry_run)


@router.get("")
def run_audit(
    start: date = Query(...), end: date = Query(...),
    employee: str | None = Query(None, max_length=80, description="an employee's name or code: only their entries"),
    show_all: bool = Query(False, description="also list the entries that are fine"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """For each entry employees logged in the window: fine, changed, cleared, missing (and why), or hidden because its store is no longer live."""
    return order_audit_service.audit(db, user, start, end, employee=employee, show_all=show_all)


@router.post("/restore")
def restore(body: RestoreIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Re-create the entries the log shows but the database lacks. dry_run (the default) only counts them."""
    return order_audit_service.restore(db, user, body.start, body.end, dry_run=body.dry_run)
