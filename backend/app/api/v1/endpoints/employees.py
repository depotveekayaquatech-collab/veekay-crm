"""Employee routes — thin wrappers over employee_service."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.employee import (
    AdminAccess,
    EmployeeCreate,
    EmployeeImportResult,
    EmployeeOut,
    EmployeeUpdate,
    PermissionSet,
)
from pydantic import BaseModel

from app.services import employee_import_service, employee_service
from app.services.store_sync_service import SyncError

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get(
    "", response_model=Page[EmployeeOut],
    dependencies=[Depends(require_permission("employees.view"))],
)
def list_employees(
    q: str | None = None,
    region_id: uuid.UUID | None = None,
    platform_id: uuid.UUID | None = None,
    category: str | None = Query(None, pattern="^(admin|accounts|partner|blinkit|zepto)$"),
    params: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[EmployeeOut]:
    return employee_service.list_employees(
        db, user, params, q=q, region_id=region_id, platform_id=platform_id, category=category
    )


@router.post(
    "/import", response_model=EmployeeImportResult,
    dependencies=[Depends(require_permission("employees.create"))],
)
async def import_employees(
    keep_sheet_passwords: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeImportResult:
    """Bulk-create employees from the old EMPLOYEES sheet (and Zepto state assignments)."""
    content = await file.read(employee_import_service.MAX_UPLOAD_BYTES + 1)
    try:
        result = employee_import_service.import_employees(
            db, user, file.filename or "", content, keep_sheet_passwords=keep_sheet_passwords
        )
    except SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return EmployeeImportResult(**result.as_dict())


class ResetPasswordOut(BaseModel):
    temp_password: str


@router.post(
    "/{employee_id}/reset-password", response_model=ResetPasswordOut,
    dependencies=[Depends(require_permission("employees.update"))],
)
def reset_password(
    employee_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResetPasswordOut:
    """Issue a one-time temporary password. The employee must choose their own at next sign-in."""
    return ResetPasswordOut(temp_password=employee_service.reset_password(db, user, employee_id))


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


@router.put(
    "/{employee_id}/admin-access", response_model=EmployeeOut,
    dependencies=[Depends(require_permission("employees.create"))],
)
def set_admin_access(
    employee_id: uuid.UUID,
    payload: AdminAccess,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return employee_service.set_admin_access(db, user, employee_id, payload.full)


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
