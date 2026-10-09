"""State-assignment + employee-scope routes."""
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.organization import Organization, OrganizationKind
from app.models.user import User
from app.schemas.employee import EmployeeOut, EmployeeScope
from app.services import assignment_service, employee_service

router = APIRouter(prefix="/assignments", tags=["assignments"])


class StateAssignRequest(BaseModel):
    partner_id: uuid.UUID
    state: str
    employee_id: uuid.UUID


@router.get(
    "/states", dependencies=[Depends(require_permission("assignments.manage"))],
)
def state_board(
    partner: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    org = db.execute(select(Organization).where(Organization.slug == partner)).scalar_one_or_none()
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        return {"assigned": [], "unassigned": [], "employees": []}
    return assignment_service.state_board(db, user, org.id)


@router.post(
    "/states", status_code=204,
    dependencies=[Depends(require_permission("assignments.manage"))],
)
def assign_state(
    payload: StateAssignRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    assignment_service.assign_state(db, user, payload.partner_id, payload.state, payload.employee_id)


@router.delete(
    "/states/{assignment_id}", status_code=204,
    dependencies=[Depends(require_permission("assignments.manage"))],
)
def unassign_state(
    assignment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    assignment_service.unassign_state(db, user, assignment_id)


@router.get(
    "/locations", dependencies=[Depends(require_permission("assignments.manage"))],
)
def locations(
    partner: str,
    region_ids: list[uuid.UUID] = Query(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """The states and cities inside the chosen regions of a platform: what an employee can be told to skip."""
    org = db.execute(select(Organization).where(Organization.slug == partner)).scalar_one_or_none()
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        return {"states": [], "cities": []}
    return assignment_service.locations(db, user, org.id, region_ids)


@router.put(
    "/scope/{employee_id}", response_model=EmployeeOut,
    dependencies=[Depends(require_permission("assignments.manage"))],
)
def set_scope(
    employee_id: uuid.UUID,
    payload: EmployeeScope,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    employee = employee_service.require_employee(db, user, employee_id)
    assignment_service.set_scope(
        db, user, employee, platform_id=payload.platform_id, region_id=payload.region_id, region_ids=payload.region_ids,
        excluded_states=payload.excluded_states, excluded_cities=payload.excluded_cities,
        included_states=payload.included_states, included_cities=payload.included_cities,
    )
    return employee_service.get_employee(db, user, employee_id)
