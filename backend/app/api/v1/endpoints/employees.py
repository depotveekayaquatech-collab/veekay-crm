"""Employee routes — thin wrappers over employee_service."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate, PermissionSet
from app.services import employee_service

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get(
    "", response_model=Page[EmployeeOut],
    dependencies=[Depends(require_permission("employees.view"))],
)
def list_employees(
    q: str | None = None,
    region_id: uuid.UUID | None = None,
    platform_id: uuid.UUID | None = None,
    params: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[EmployeeOut]:
    return employee_service.list_employees(
        db, user, params, q=q, region_id=region_id, platform_id=platform_id
    )


@router.post(
    "", response_model=EmployeeOut, status_code=201,
    dependencies=[Depends(require_permission("employees.create"))],
)
def create_employee(
    payload: EmployeeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return employee_service.create_employee(db, user, payload)


@router.get(
    "/{employee_id}", response_model=EmployeeOut,
    dependencies=[Depends(require_permission("employees.view"))],
)
def get_employee(
    employee_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return employee_service.get_employee(db, user, employee_id)


@router.patch(
    "/{employee_id}", response_model=EmployeeOut,
    dependencies=[Depends(require_permission("employees.update"))],
)
def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return employee_service.update_employee(db, user, employee_id, payload)


@router.put(
    "/{employee_id}/permissions", response_model=EmployeeOut,
    dependencies=[Depends(require_permission("employees.create"))],
)
def set_permissions(
    employee_id: uuid.UUID,
    payload: PermissionSet,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return employee_service.set_permissions(db, user, employee_id, payload.codes)


@router.post(
    "/{employee_id}/deactivate", status_code=204,
    dependencies=[Depends(require_permission("employees.deactivate"))],
)
def deactivate_employee(
    employee_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    employee_service.deactivate_employee(db, user, employee_id)
