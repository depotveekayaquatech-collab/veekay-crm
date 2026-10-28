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
    """A new capping for one store. The names are camelCase (storeId); snake_case works too."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    store_id: uuid.UUID = Field(alias="storeId")
    capping: StrictInt = Field(ge=1, le=capping_service.MAX_CAP, description="bottles per day")


class RemoveCappingIn(BaseModel):
    """Remove a store's capping. camelCase (storeId); snake_case works too."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    store_id: uuid.UUID = Field(alias="storeId")



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
    """Administrator / manager (capping.change): set a store's capping. It applies from today (a store's first capping from the day its entries started); every
    change is kept in the history. There is no date to choose and no delete."""
    return capping_history_service.change(db, user, perms, payload.store_id, payload.capping)


@router.post("/remove", status_code=status.HTTP_201_CREATED)
def remove_capping(
    payload: RemoveCappingIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Administrator / manager (capping.change): remove a store's capping. It is recorded in the history as a change to "no capping"; earlier days keep theirs."""
    return capping_history_service.remove_capping(db, user, perms, payload.store_id)


@router.get("/alert")
def get_alert(
    from_: date | None = Query(None, alias="from", description="first date; the 1st of this month by default"),
    to: date | None = Query(None, description="last date; the end of this month by default"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """The "Reduce capping" alert: the collective average entry and average capping of all live Zepto stores against MAX_DAILY_LIMIT."""
    return capping_history_service.alert_summary(db, user, perms, from_, to)


@router.get("/history")
def get_history(
    store_id: uuid.UUID = Query(alias="storeId"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """One store's capping changes, newest effective date first."""
    return capping_history_service.history(db, user, perms, store_id)
