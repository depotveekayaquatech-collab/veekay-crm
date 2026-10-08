"""
Employee management. An "employee" is a User in the caller's organization
holding the 'employee' role. Admins create them with an Employee ID + an
initial password and a set of permissions (what they can see/do).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, CATEGORY_LABELS, MANAGER, PARTNER, PARTNER_PERMISSIONS, staff_category
from app.core.security import generate_temp_password, hash_password
from app.models.organization import Organization, OrganizationKind
from app.models.permission import Permission
from app.models.role import Role
from app.models.state_assignment import StateAssignment
from app.models.user_permission import UserPermission
from app.models.user import User, UserRole, UserStatus
from app.repositories.employee_repository import EMPLOYEE_ROLE_CODE, EmployeeRepository
from app.repositories.region_repository import RegionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import Page, PageParams
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.services import activity_service, session_service


def to_out(db: Session, user: User) -> EmployeeOut:
    erepo = EmployeeRepository(db)
    urepo = UserRepository(db)
    roles = erepo.role_codes(user.id)
    category = staff_category(roles, user.platform_organization.slug if user.platform_organization else None)
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
        roles=roles,
        category=category,
        category_label=CATEGORY_LABELS[category],
        admin_level="full" if ADMIN in roles else ("custom" if MANAGER in roles else None),
        direct_permissions=sorted(urepo.get_direct_permission_codes(user.id)),
    )


def to_out_many(db: Session, users: list[User]) -> list[EmployeeOut]:
    """`to_out` for a whole page: roles, states and direct permissions in three queries instead of three per person."""
    if not users:
        return []
    ids = [u.id for u in users]
    roles: dict[uuid.UUID, list[str]] = {}
    for uid, code in db.execute(
        select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id.in_(ids))
    ):
        roles.setdefault(uid, []).append(code)
    states: dict[uuid.UUID, list[str]] = {}
    for uid, st in db.execute(
        select(StateAssignment.assigned_user_id, StateAssignment.state)
        .where(StateAssignment.assigned_user_id.in_(ids))
        .order_by(StateAssignment.state)
    ):
        states.setdefault(uid, []).append(st)
    direct: dict[uuid.UUID, list[str]] = {}
    for uid, code in db.execute(
        select(UserPermission.user_id, Permission.code)
        .join(Permission, Permission.id == UserPermission.permission_id)
        .where(UserPermission.user_id.in_(ids))
    ):
        direct.setdefault(uid, []).append(code)

    out = []
    for user in users:
        r = roles.get(user.id, [])
        slug = user.platform_organization.slug if user.platform_organization else None
        category = staff_category(r, slug)
        out.append(EmployeeOut(
            id=user.id, employee_code=user.employee_code, full_name=user.full_name, email=user.email, phone=user.phone,
            status=user.status, is_active=user.is_active, platform_id=user.platform_organization_id, platform_slug=slug,
            region_id=user.region_id, region_name=user.region.name if user.region else None,
            states=states.get(user.id, []), roles=r, category=category, category_label=CATEGORY_LABELS[category],
            admin_level="full" if ADMIN in r else ("custom" if MANAGER in r else None),
            direct_permissions=sorted(direct.get(user.id, [])),
        ))
    return out


def list_employees(
    db: Session,
    actor: User,
    params: PageParams,
    *,
    q: str | None = None,
    region_id: uuid.UUID | None = None,
    platform_id: uuid.UUID | None = None,
    category: str | None = None,
) -> Page[EmployeeOut]:
    users, total = EmployeeRepository(db).list(
        actor.organization_id, offset=params.offset, limit=params.limit,
        q=q, region_id=region_id, platform_id=platform_id, category=category,
    )
    return Page(
        items=to_out_many(db, users),
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
    is_partner = payload.account_type == "partner"
    is_admin_account = payload.account_type == "admin"
    if is_admin_account:
        _require_full_admin(db, actor, "Only an admin can create another admin.")
    if payload.permission_codes and not (is_admin_account and payload.admin_access == "full"):
        _check_grantable(db, actor, payload.permission_codes)
    if is_partner:
        if payload.platform_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the platform (Blinkit or Zepto) for this partner account.")
        _check_partner_permissions(payload.permission_codes)
    if payload.region_id is not None and not (is_partner or is_admin_account):
        _validate_region(db, actor, payload.region_id)
    if payload.platform_id is not None and not is_admin_account:
        _validate_platform(db, payload.platform_id)

    if is_admin_account:
        role_code = ADMIN if payload.admin_access == "full" else MANAGER
    else:
        role_code = PARTNER if is_partner else EMPLOYEE_ROLE_CODE
    role = db.execute(select(Role).where(Role.code == role_code)).scalar_one_or_none()
    if role is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"The '{role_code}' role is not configured. Run the latest migration.")

    user = User(
        organization_id=actor.organization_id,
        platform_organization_id=None if is_admin_account else payload.platform_id,
        region_id=None if (is_partner or is_admin_account) else payload.region_id,
        employee_code=payload.employee_code.strip(),
        full_name=payload.full_name,
        email=payload.email.lower() if payload.email else None,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        must_change_password=True,  # the admin chose it, so the person must replace it
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    if payload.permission_codes and not (is_admin_account and payload.admin_access == "full"):
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
        user.must_change_password = True
        session_service.revoke_user_sessions(db, user.id)  # old devices are signed out
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
    target_roles = EmployeeRepository(db).role_codes(user.id)
    if PARTNER in target_roles:
        _check_partner_permissions(codes)
    if ADMIN in target_roles:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "A full admin already has every permission. Switch them to custom access first.",
        )
    _check_grantable(db, actor, codes)
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
    if ADMIN in EmployeeRepository(db).role_codes(user.id) and EmployeeRepository(db).active_full_admin_count(actor.organization_id) <= 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This is the only full admin; keep at least one.")
    user.is_active = False
    user.status = UserStatus.DEACTIVATED.value
    session_service.revoke_user_sessions(db, user.id)
    activity_service.record(
        db, actor=actor, action="employee.deactivated", entity_type="employee", entity_id=user.id,
    )
    db.commit()


def _is_full_admin(db: Session, actor: User) -> bool:
    return ADMIN in EmployeeRepository(db).role_codes(actor.id)


def _require_full_admin(db: Session, actor: User, message: str) -> None:
    if not _is_full_admin(db, actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)


def _check_grantable(db: Session, actor: User, codes: list[str]) -> None:
    """Nobody can hand out a permission they do not hold themselves (a custom admin cannot mint a stronger one)."""
    if _is_full_admin(db, actor):
        return
    extra = sorted(set(codes) - UserRepository(db).get_permission_codes(actor.id))
    if extra:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"You can't grant permissions you don't have: {', '.join(extra)}.")


def require_employee(db: Session, actor: User, employee_id: uuid.UUID) -> User:
    full = _is_full_admin(db, actor)
    user = EmployeeRepository(db).get(actor.organization_id, employee_id, include_admins=full)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    if not full and MANAGER in EmployeeRepository(db).role_codes(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can change another admin's account.")
    return user


def set_admin_access(db: Session, actor: User, employee_id: uuid.UUID, full: bool) -> EmployeeOut:
    """Switch an admin between full power (the Admin role) and custom access (only the permissions ticked for them)."""
    _require_full_admin(db, actor, "Only an admin can change admin access.")
    user = require_employee(db, actor, employee_id)
    repo = EmployeeRepository(db)
    roles = repo.role_codes(user.id)
    if ADMIN not in roles and MANAGER not in roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This account isn't an admin.")
    if not full and ADMIN in roles and (user.id == actor.id or repo.active_full_admin_count(actor.organization_id) <= 1):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Keep at least one full admin (and you can't reduce your own access).",
        )
    target = db.execute(select(Role).where(Role.code == (ADMIN if full else MANAGER))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Run the latest database migration.")
    for ur in list(user.user_roles):
        if ur.role.code in (ADMIN, MANAGER):
            db.delete(ur)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=target.id))
    if full:
        UserRepository(db).set_direct_permissions(user.id, [])  # the role covers everything
    activity_service.record(
        db, actor=actor, action="employee.admin_access_set", entity_type="employee", entity_id=user.id,
        metadata={"level": "full" if full else "custom"},
    )
    db.commit()
    db.expire_all()
    return get_employee(db, actor, employee_id)


def _check_partner_permissions(codes: list[str]) -> None:
    """Partner accounts can never be given staff-wide permissions (overview, stores, team ...)."""
    extra = sorted(set(codes) - set(PARTNER_PERMISSIONS))
    if extra:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Partner accounts can't hold: {', '.join(extra)}.",
        )


def _validate_region(db: Session, actor: User, region_id: uuid.UUID) -> None:
    if RegionRepository(db).get(actor.organization_id, region_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid region.")


def _validate_platform(db: Session, platform_id: uuid.UUID) -> None:
    org = db.get(Organization, platform_id)
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid platform.")


def reset_password(db: Session, actor: User, employee_id: uuid.UUID) -> str:
    """Give an employee a new random temporary password (returned once), unlock the account,
    sign every device out and require a change at next sign-in."""
    user = require_employee(db, actor, employee_id)
    temp = generate_temp_password()
    user.password_hash = hash_password(temp)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    if user.status == UserStatus.LOCKED.value:
        user.status = UserStatus.ACTIVE.value
    session_service.revoke_user_sessions(db, user.id)
    activity_service.record(
        db, actor=actor, action="employee.password_reset", entity_type="employee", entity_id=user.id,
        metadata={"employee_code": user.employee_code},  # never the password
    )
    db.commit()
    return temp
