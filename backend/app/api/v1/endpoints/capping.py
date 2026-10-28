"""Zepto capping: every live store with its latest capping, a way to update it (a new value from a date, or a corrected start date), and each store's history.
Everything else (usage levels, alerts, uploads, sheets, averages) was removed on purpose: the page keeps only the capping and its record."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import capping_history_service, capping_service

router = APIRouter(prefix="/capping", tags=["capping"])


class CappingChangeIn(BaseModel):
    """A new capping for one store from a date. The names are camelCase (storeId, effectiveFrom); snake_case works too."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    store_id: uuid.UUID = Field(alias="storeId")
    capping: StrictInt = Field(ge=1, le=capping_service.MAX_CAP, description="bottles per day, from the effective date")
    effective_from: date = Field(alias="effectiveFrom", description="today or an earlier date (Asia/Kolkata)")


class EffectiveDateIn(BaseModel):
    """Move a capping change to another start date. camelCase (effectiveFrom); snake_case works too."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    effective_from: date = Field(alias="effectiveFrom")


@router.get("")
def list_capping(
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Every live Zepto store with its latest capping and the date it started."""
    return capping_history_service.current_list(db, user, perms)


@router.post("/change", status_code=status.HTTP_201_CREATED)
def change_capping(
    payload: CappingChangeIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Administrator / manager (capping.change): a store's capping from a date. A past date is allowed (`backdated` is true so the page can have asked first);
    a date that already has a change for the store is refused with 409. There is no delete."""
    return capping_history_service.change(db, user, perms, payload.store_id, payload.capping, payload.effective_from)


@router.get("/history")
def get_history(
    store_id: uuid.UUID = Query(alias="storeId"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """One store's capping changes, newest effective date first."""
    return capping_history_service.history(db, user, perms, store_id)


@router.patch("/history/{history_id}")
def change_history_date(
    history_id: uuid.UUID, payload: EffectiveDateIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Administrator / manager (capping.change): move one capping change to another start date. Only the date can change (the capping value cannot); a date that
    already has a change for the store is refused with 409, and the change is recorded in the activity log."""
    return capping_history_service.change_effective_date(db, user, perms, history_id, payload.effective_from)
