"""
Resolves which stores a field employee can see, and manages the two
assignment models:

  - region-model (e.g. Blinkit): employee -> one region. Sees every LIVE
    store in it, UNLESS the region has been "partitioned" — i.e. at least
    one state within it is assigned to someone — in which case each
    employee sees only the states assigned to them and unassigned states
    in that region are invisible to everyone.
  - employee-model (e.g. Zepto, per settings.EMPLOYEE_MODEL_PLATFORM_SLUGS):
    no region. Sees every LIVE store whose state is assigned to them.

Fail-open: if scope can't be resolved the caller gets an empty list, never
an exception.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import PARTNER as PARTNER_ROLE
from app.models.organization import Organization, OrganizationKind
from app.models.region import Region
from app.models.state_assignment import StateAssignment
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.region_repository import RegionRepository
from app.repositories.user_repository import UserRepository
from app.services import activity_service


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _platform(db: Session, partner_id: uuid.UUID) -> Organization:
    org = db.get(Organization, partner_id)
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid platform.")
    return org


def is_employee_model(platform_slug: str | None) -> bool:
    return _norm(platform_slug) in {s.lower() for s in settings.EMPLOYEE_MODEL_PLATFORM_SLUGS}


def is_region_independent(platform_slug: str | None) -> bool:
    return _norm(platform_slug) in {s.lower() for s in settings.REGION_INDEPENDENT_PLATFORM_SLUGS}


# --------------------------------------------------------------------------
# store visibility
# --------------------------------------------------------------------------

def is_partner_account(db: Session, user: User) -> bool:
    return PARTNER_ROLE in UserRepository(db).get_role_codes(user.id)


def visible_stores(db: Session, employee: User) -> list[Store]:
    partner_id = employee.platform_organization_id
    if partner_id is None:
        return []
    if is_partner_account(db, employee):
        # A Blinkit / Zepto login sees every live store of its own platform — no region or state scoping.
        rows = db.execute(
            select(Store).where(
                Store.organization_id == employee.organization_id,
                Store.partner_organization_id == partner_id,
                Store.status == StoreStatus.LIVE.value,
            )
        ).scalars().all()
        return _load(db, list(rows))
    platform = db.get(Organization, partner_id)
    slug = platform.slug if platform else None

    assignments = db.execute(
        select(StateAssignment).where(StateAssignment.partner_organization_id == partner_id)
    ).scalars().all()
    my_states = {_norm(a.state) for a in assignments if a.assigned_user_id == employee.id}

    live = select(Store).where(
        Store.organization_id == employee.organization_id,
        Store.partner_organization_id == partner_id,
        Store.status == StoreStatus.LIVE.value,
    )

    if is_employee_model(slug):
        if not my_states:
            return []
        rows = db.execute(live.where(func.lower(Store.state).in_(my_states))).scalars().all()
        return _load(db, rows)

    # region-model
    if employee.region_id is None:
        return []
    region_stores = db.execute(live.where(Store.region_id == employee.region_id)).scalars().all()
    assigned_states_in_platform = {_norm(a.state) for a in assignments}
    region_states = {_norm(s.state) for s in region_stores if s.state}
    partitioned = bool(region_states & assigned_states_in_platform)
    if not partitioned:
        return _load(db, region_stores)
    return _load(db, [s for s in region_stores if _norm(s.state) in my_states])


def _load(db: Session, stores: list[Store]) -> list[Store]:
    if not stores:
        return []
    ids = [s.id for s in stores]
    from sqlalchemy.orm import joinedload

    stmt = (
        select(Store)
        .where(Store.id.in_(ids))
        .options(joinedload(Store.region), joinedload(Store.partner_organization))
        .order_by(Store.name)
    )
    return list(db.execute(stmt).unique().scalars().all())


def visible_store_ids(db: Session, employee: User) -> set[uuid.UUID]:
    return {s.id for s in visible_stores(db, employee)}


# --------------------------------------------------------------------------
# admin: employee scope
# --------------------------------------------------------------------------

def set_scope(
    db: Session,
    admin: User,
    employee: User,
    *,
    platform_id: uuid.UUID | None,
    region_id: uuid.UUID | None,
) -> None:
    if platform_id is not None:
        _platform(db, platform_id)
    if region_id is not None and RegionRepository(db).get(admin.organization_id, region_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid region.")
    employee.platform_organization_id = platform_id
    employee.region_id = None if is_partner_account(db, employee) else region_id
    activity_service.record(
        db, actor=admin, action="employee.scope_set", entity_type="employee", entity_id=employee.id,
        metadata={"platform_id": str(platform_id) if platform_id else None,
                  "region_id": str(region_id) if region_id else None},
    )
    db.commit()


# --------------------------------------------------------------------------
# admin: state assignment board
# --------------------------------------------------------------------------

def _state_region_map(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID) -> dict[str, str | None]:
    rows = db.execute(
        select(func.lower(Store.state), Region.name)
        .join(Region, Region.id == Store.region_id)
        .where(Store.organization_id == org_id, Store.partner_organization_id == partner_id, Store.state.isnot(None))
        .distinct()
    ).all()
    out: dict[str, str | None] = {}
    for state, region_name in rows:
        out.setdefault(state, region_name)
    return out


def state_board(db: Session, admin: User, partner_id: uuid.UUID) -> dict:
    _platform(db, partner_id)
    org_id = admin.organization_id

    # every distinct state + its LIVE store count
    counts = dict(
        db.execute(
            select(func.lower(Store.state), func.count(Store.id))
            .where(
                Store.organization_id == org_id,
                Store.partner_organization_id == partner_id,
                Store.state.isnot(None),
                Store.status == StoreStatus.LIVE.value,
            )
            .group_by(func.lower(Store.state))
        ).all()
    )
    display = dict(
        db.execute(
            select(func.lower(Store.state), func.max(Store.state))
            .where(Store.organization_id == org_id, Store.partner_organization_id == partner_id, Store.state.isnot(None))
            .group_by(func.lower(Store.state))
        ).all()
    )
    region_map = _state_region_map(db, org_id, partner_id)

    assignments = db.execute(
        select(StateAssignment, User.full_name)
        .join(User, User.id == StateAssignment.assigned_user_id)
        .where(StateAssignment.partner_organization_id == partner_id)
    ).all()
    assigned_by_state = {_norm(a.state): (a, name) for a, name in assignments}

    assigned, unassigned = [], []
    for key in sorted(set(counts) | set(display) | set(assigned_by_state)):
        row = {
            "state": display.get(key, key.title()),
            "region_name": region_map.get(key),
            "store_count": counts.get(key, 0),
        }
        if key in assigned_by_state:
            a, name = assigned_by_state[key]
            assigned.append({**row, "assignment_id": str(a.id),
                             "employee_id": str(a.assigned_user_id), "employee_name": name})
        else:
            unassigned.append(row)

    employees = [
        {"id": str(u.id), "name": u.full_name, "employee_code": u.employee_code}
        for u in EmployeeRepository(db).all_for_platform(org_id, partner_id)
    ]
    return {
        "assigned": assigned,
        "unassigned": unassigned,
        "employees": employees,
        "assigned_state_count": len(assigned),
        "unassigned_state_count": len(unassigned),
        "assigned_store_count": sum(r["store_count"] for r in assigned),
        "unassigned_store_count": sum(r["store_count"] for r in unassigned),
    }


def assign_state(db: Session, admin: User, partner_id: uuid.UUID, state: str, employee_id: uuid.UUID) -> None:
    platform = _platform(db, partner_id)
    employee = EmployeeRepository(db).get(admin.organization_id, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid employee.")
    if employee.platform_organization_id != partner_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Employee is not on this platform.")

    if not is_region_independent(platform.slug):
        region_map = _state_region_map(db, admin.organization_id, partner_id)
        state_region = region_map.get(_norm(state))
        emp_region = employee.region.name if employee.region else None
        if state_region and emp_region and state_region != emp_region:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"'{state}' is in {state_region}, but this employee is in {emp_region}.",
            )

    existing = db.execute(
        select(StateAssignment).where(
            StateAssignment.partner_organization_id == partner_id,
            func.lower(StateAssignment.state) == state.strip().lower(),
        )
    ).scalar_one_or_none()
    if existing:
        existing.assigned_user_id = employee.id
    else:
        db.add(StateAssignment(
            organization_id=admin.organization_id,
            partner_organization_id=partner_id,
            state=state.strip(),
            assigned_user_id=employee.id,
        ))
    activity_service.record(
        db, actor=admin, action="state.assigned", entity_type="state_assignment", entity_id=state.strip(),
        metadata={"state": state.strip(), "employee": employee.full_name},
    )
    db.commit()


def unassign_state(db: Session, admin: User, assignment_id: uuid.UUID) -> None:
    a = db.get(StateAssignment, assignment_id)
    if a is None or a.organization_id != admin.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    state = a.state
    db.delete(a)
    activity_service.record(
        db, actor=admin, action="state.unassigned", entity_type="state_assignment", entity_id=state,
        metadata={"state": state},
    )
    db.commit()
