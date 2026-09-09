"""
Employee management. An "employee" is a User in the caller's organization
holding the 'employee' role. Admins create them with an Employee ID + an
initial password and a set of permissions (what they can see/do).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.organization import Organization, OrganizationKind
from app.models.role import Role
from app.models.user import User, UserRole, UserStatus
from app.repositories.employee_repository import EMPLOYEE_ROLE_CODE, EmployeeRepository
from app.repositories.region_repository import RegionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import Page, PageParams
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.services import activity_service


def to_out(db: Session, user: User) -> EmployeeOut:
    erepo = EmployeeRepository(db)
    urepo = UserRepository(db)
    return EmployeeOut(
        id=user.id,
        employee_code=user.employee_code,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        is_active=user.is_active,
        platform_id=user.platform_organization_id,
        platform_slug=user.platform_organization.slug if user.platform_organization else None,
        region_id=user.region_id,
        region_name=user.region.name if user.region else None,
        states=erepo.states_for(user.id),
        roles=erepo.role_codes(user.id),
        direct_permissions=sorted(urepo.get_direct_permission_codes(user.id)),
    )


def list_employees(
    db: Session,
    actor: User,
    params: PageParams,
    *,
    q: str | None = None,
    region_id: uuid.UUID | None = None,
    platform_id: uuid.UUID | None = None,
) -> Page[EmployeeOut]:
    users, total = EmployeeRepository(db).list(
        actor.organization_id, offset=params.offset, limit=params.limit,
        q=q, region_id=region_id, platform_id=platform_id,
    )
    return Page(
        items=[to_out(db, u) for u in users],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


def get_employee(db: Session, actor: User, employee_id: uuid.UUID) -> EmployeeOut:
    return to_out(db, require_employee(db, actor, employee_id))


def create_employee(db: Session, actor: User, payload: EmployeeCreate) -> EmployeeOut:
    erepo = EmployeeRepository(db)
    urepo = UserRepository(db)
    if urepo.code_exists(actor.organization_id, payload.employee_code):
        raise HTTPException(status.HTTP_409_CONFLICT, "An employee with this ID already exists.")
    if payload.email and erepo.email_exists(actor.organization_id, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists.")
    if payload.region_id is not None:
        _validate_region(db, actor, payload.region_id)
    if payload.platform_id is not None:
        _validate_platform(db, payload.platform_id)

    role = db.execute(select(Role).where(Role.code == EMPLOYEE_ROLE_CODE)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Employee role is not configured.")

    user = User(
        organization_id=actor.organization_id,
        platform_organization_id=payload.platform_id,
        region_id=payload.region_id,
        employee_code=payload.employee_code.strip(),
        full_name=payload.full_name,
        email=payload.email.lower() if payload.email else None,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if payload.permission_codes:
        urepo.set_direct_permissions(user.id, payload.permission_codes)
    activity_service.record(
        db, actor=actor, action="employee.created", entity_type="employee", entity_id=user.id,
        metadata={"employee_code": user.employee_code, "full_name": user.full_name},
    )
    db.commit()
    return get_employee(db, actor, user.id)


def update_employee(
    db: Session, actor: User, employee_id: uuid.UUID, payload: EmployeeUpdate
) -> EmployeeOut:
    user = require_employee(db, actor, employee_id)
    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data.pop("password"))
    if "email" in data and data["email"]:
        data["email"] = data["email"].lower()
    for field, value in data.items():
        setattr(user, field, value)
    activity_service.record(
        db, actor=actor, action="employee.updated", entity_type="employee", entity_id=user.id,
        metadata={k: str(v) for k, v in data.items() if k != "password"},
    )
    db.commit()
    return get_employee(db, actor, employee_id)


def set_permissions(db: Session, actor: User, employee_id: uuid.UUID, codes: list[str]) -> EmployeeOut:
    user = require_employee(db, actor, employee_id)
    UserRepository(db).set_direct_permissions(user.id, codes)
    activity_service.record(
        db, actor=actor, action="employee.permissions_set", entity_type="employee", entity_id=user.id,
        metadata={"count": len(codes)},
    )
    db.commit()
    return get_employee(db, actor, employee_id)


def deactivate_employee(db: Session, actor: User, employee_id: uuid.UUID) -> None:
    user = require_employee(db, actor, employee_id)
    if user.id == actor.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot deactivate yourself.")
    user.is_active = False
    user.status = UserStatus.DEACTIVATED.value
    activity_service.record(
        db, actor=actor, action="employee.deactivated", entity_type="employee", entity_id=user.id,
    )
    db.commit()


def require_employee(db: Session, actor: User, employee_id: uuid.UUID) -> User:
    user = EmployeeRepository(db).get(actor.organization_id, employee_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    return user


def _validate_region(db: Session, actor: User, region_id: uuid.UUID) -> None:
    if RegionRepository(db).get(actor.organization_id, region_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid region.")


def _validate_platform(db: Session, platform_id: uuid.UUID) -> None:
    org = db.get(Organization, platform_id)
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid platform.")
