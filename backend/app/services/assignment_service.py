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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import PARTNER as PARTNER_ROLE
from app.models.organization import Organization, OrganizationKind
from app.models.employee_scope import EmployeeExclusion, EmployeeRegion, ExclusionKind, ScopeMode
from app.models.region import Region
from app.models.state_assignment import StateAssignment
from app.models.store import Store, StoreStatus
from app.models.role import Role
from app.models.user import User, UserRole
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
# multi-region scope + exclusions
# --------------------------------------------------------------------------

def employee_region_ids(db: Session, employee: User) -> set[uuid.UUID]:
    """Every region the employee covers: the ones ticked for them, plus their main region."""
    ids = set(db.execute(select(EmployeeRegion.region_id).where(EmployeeRegion.user_id == employee.id)).scalars().all())
    if employee.region_id:
        ids.add(employee.region_id)
    return ids


def employee_exclusions(db: Session, user_id: uuid.UUID) -> tuple[set[str], set[str]]:
    """(skipped states, skipped cities), lower-cased."""
    states: set[str] = set()
    cities: set[str] = set()
    for kind, value in db.execute(
        select(EmployeeExclusion.kind, EmployeeExclusion.value).where(EmployeeExclusion.user_id == user_id, EmployeeExclusion.mode == ScopeMode.SKIP)
    ):
        (states if kind == ExclusionKind.STATE else cities).add(value)
    return states, cities


def employee_additions(db: Session, user_id: uuid.UUID) -> tuple[set[str], set[str]]:
    """(added states, added cities), lower-cased: given on top of the regions, or on their own."""
    states: set[str] = set()
    cities: set[str] = set()
    for kind, value in db.execute(
        select(EmployeeExclusion.kind, EmployeeExclusion.value).where(EmployeeExclusion.user_id == user_id, EmployeeExclusion.mode == ScopeMode.ADD)
    ):
        (states if kind == ExclusionKind.STATE else cities).add(value)
    return states, cities


def _drop_excluded(stores: list[Store], ex_states: set[str], ex_cities: set[str]) -> list[Store]:
    if not ex_states and not ex_cities:
        return stores
    return [s for s in stores if _norm(s.state) not in ex_states and _norm(s.city) not in ex_cities]


# --------------------------------------------------------------------------
# store visibility
# --------------------------------------------------------------------------

def is_partner_account(db: Session, user: User) -> bool:
    return PARTNER_ROLE in UserRepository(db).get_role_codes(user.id)


def all_live_stores(db: Session, user: User) -> list[Store]:
    """Every live store in the organisation, on every platform — what an admin (orders.correct) works with."""
    rows = db.execute(
        select(Store).where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
    ).scalars().all()
    return _load(db, list(rows))


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

    ex_states, ex_cities = employee_exclusions(db, employee.id)
    add_states, add_cities = employee_additions(db, employee.id)
    added = (
        list(db.execute(live.where(or_(func.lower(Store.state).in_(add_states), func.lower(Store.city).in_(add_cities)))).scalars().all())
        if (add_states or add_cities) else []
    )

    if is_employee_model(slug):
        rows = list(db.execute(live.where(func.lower(Store.state).in_(my_states))).scalars().all()) if my_states else []
        merged = {s.id: s for s in rows + added}
        return _load(db, _drop_excluded(list(merged.values()), ex_states, ex_cities))

    # region-model: every region the employee covers; a region where states are handed out one by one ("partitioned")
    # only gives the employee the states assigned to them; then the excluded states / cities are taken out.
    region_ids = employee_region_ids(db, employee)
    region_stores = list(db.execute(live.where(Store.region_id.in_(region_ids))).scalars().all()) if region_ids else []
    assigned_states_in_platform = {_norm(a.state) for a in assignments}
    states_by_region: dict[uuid.UUID, set[str]] = {}
    for st in region_stores:
        if st.state:
            states_by_region.setdefault(st.region_id, set()).add(_norm(st.state))
    partitioned = {rid for rid, sts in states_by_region.items() if sts & assigned_states_in_platform}
    kept = [st for st in region_stores if st.region_id not in partitioned or _norm(st.state) in my_states]
    merged = {s.id: s for s in kept + added}          # places added by hand are given whatever the region partition says
    return _load(db, _drop_excluded(list(merged.values()), ex_states, ex_cities))


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
    region_ids: list[uuid.UUID] | None = None,
    excluded_states: list[str] | None = None,
    excluded_cities: list[str] | None = None,
    included_states: list[str] | None = None,
    included_cities: list[str] | None = None,
) -> None:
    """Platform + regions + places. `region_ids` (several regions) wins over `region_id`. Skipped / added states and
    cities left as None stay as they are, [] clears them. Skipping always wins over adding."""
    if platform_id is not None:
        _platform(db, platform_id)
    wanted = list(dict.fromkeys(region_ids if region_ids is not None else ([region_id] if region_id else [])))
    for rid in wanted:
        if RegionRepository(db).get(admin.organization_id, rid) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid region.")
    if is_partner_account(db, employee):
        wanted = []
    employee.platform_organization_id = platform_id
    employee.region_id = wanted[0] if wanted else None
    db.query(EmployeeRegion).filter(EmployeeRegion.user_id == employee.id).delete()
    for rid in wanted:
        db.add(EmployeeRegion(user_id=employee.id, region_id=rid))

    for mode, states_in, cities_in in (
        (ScopeMode.SKIP, excluded_states, excluded_cities),
        (ScopeMode.ADD, included_states, included_cities),
    ):
        for kind, values in ((ExclusionKind.STATE, states_in), (ExclusionKind.CITY, cities_in)):
            if values is None:
                continue                                   # left out = unchanged
            db.query(EmployeeExclusion).filter(
                EmployeeExclusion.user_id == employee.id, EmployeeExclusion.mode == mode, EmployeeExclusion.kind == kind
            ).delete(synchronize_session=False)
            seen: set[str] = set()
            for raw in values:
                label = " ".join((raw or "").split())
                if label and _norm(label) not in seen:
                    seen.add(_norm(label))
                    db.add(EmployeeExclusion(user_id=employee.id, mode=mode, kind=kind, value=_norm(label), label=label))
    activity_service.record(
        db, actor=admin, action="employee.scope_set", entity_type="employee", entity_id=employee.id,
        metadata={"platform_id": str(platform_id) if platform_id else None,
                  "region_ids": [str(r) for r in wanted],
                  "excluded_states": excluded_states, "excluded_cities": excluded_cities,
                  "included_states": included_states, "included_cities": included_cities},
    )
    db.commit()


def locations(db: Session, admin: User, partner_id: uuid.UUID, region_ids: list[uuid.UUID]) -> dict:
    """The states and cities inside the chosen regions of a platform: what can be excluded."""
    _platform(db, partner_id)
    stmt = select(Store.state, Store.city).where(
        Store.organization_id == admin.organization_id, Store.partner_organization_id == partner_id,
    )
    if region_ids:
        stmt = stmt.where(Store.region_id.in_(region_ids))
    states: dict[str, str] = {}
    cities: dict[str, dict] = {}
    for state, city in db.execute(stmt.distinct()).all():
        if state and state.strip():
            states.setdefault(_norm(state), state.strip())
        if city and city.strip():
            cities.setdefault(_norm(city), {"city": city.strip(), "state": (state or "").strip()})
    return {
        "states": sorted(states.values()),
        "cities": sorted(cities.values(), key=lambda c: (c["city"].lower(), c["state"].lower())),
    }


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
        emp_region_ids = employee_region_ids(db, employee)
        emp_regions = {n for (n,) in db.execute(select(Region.name).where(Region.id.in_(emp_region_ids))).all()} if emp_region_ids else set()
        if state_region and emp_regions and state_region not in emp_regions:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"'{state}' is in {state_region}, but this employee covers {', '.join(sorted(emp_regions))}.",
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


def employee_store_scopes(
    db: Session, partner: Organization, employees: list[User]
) -> tuple[dict[uuid.UUID, list[uuid.UUID]], list[uuid.UUID]]:
    """Which live stores each employee of `partner` can see, for ALL of them in three queries (roles, the
    platform's live stores, its state assignments) instead of three to five queries per employee.

    Same rules as `visible_stores` (partner login: whole platform; employee-model platform: assigned states;
    region platform: own region, narrowed to assigned states when the platform has partitioned them).
    Returns ({user_id: [store_id, ...]}, [every live store id of the platform])."""
    live = db.execute(
        select(Store.id, Store.state, Store.region_id, Store.city).where(
            Store.partner_organization_id == partner.id, Store.status == StoreStatus.LIVE.value
        )
    ).all()
    all_ids = [r[0] for r in live]
    if not employees:
        return {}, all_ids

    ids = [e.id for e in employees]
    roles: dict[uuid.UUID, set[str]] = {}
    for uid, code in db.execute(
        select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id.in_(ids))
    ):
        roles.setdefault(uid, set()).add(code)

    assignments = db.execute(
        select(StateAssignment.assigned_user_id, StateAssignment.state).where(
            StateAssignment.partner_organization_id == partner.id
        )
    ).all()
    platform_states = {_norm(st) for _, st in assignments}
    states_of: dict[uuid.UUID, set[str]] = {}
    for uid, st in assignments:
        states_of.setdefault(uid, set()).add(_norm(st))

    regions_of: dict[uuid.UUID, set[uuid.UUID]] = {e.id: ({e.region_id} if e.region_id else set()) for e in employees}
    for uid, rid in db.execute(select(EmployeeRegion.user_id, EmployeeRegion.region_id).where(EmployeeRegion.user_id.in_(ids))):
        regions_of[uid].add(rid)
    ex_states_of: dict[uuid.UUID, set[str]] = {}
    ex_cities_of: dict[uuid.UUID, set[str]] = {}
    add_states_of: dict[uuid.UUID, set[str]] = {}
    add_cities_of: dict[uuid.UUID, set[str]] = {}
    for uid, kind, mode, value in db.execute(
        select(EmployeeExclusion.user_id, EmployeeExclusion.kind, EmployeeExclusion.mode, EmployeeExclusion.value).where(EmployeeExclusion.user_id.in_(ids))
    ):
        if mode == ScopeMode.SKIP:
            (ex_states_of if kind == ExclusionKind.STATE else ex_cities_of).setdefault(uid, set()).add(value)
        else:
            (add_states_of if kind == ExclusionKind.STATE else add_cities_of).setdefault(uid, set()).add(value)

    employee_model = is_employee_model(partner.slug)
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for emp in employees:
        mine = states_of.get(emp.id, set())
        ex_s, ex_c = ex_states_of.get(emp.id, set()), ex_cities_of.get(emp.id, set())
        if PARTNER_ROLE in roles.get(emp.id, set()):
            out[emp.id] = list(all_ids)
            continue
        if employee_model:
            pool = [(sid, st, ct) for sid, st, _, ct in live if _norm(st) in mine] if mine else []
            region = []
        else:
            my_regions = regions_of.get(emp.id, set())
            region = [(sid, st, ct, rid) for sid, st, rid, ct in live if rid in my_regions]
            states_by_region: dict[uuid.UUID, set[str]] = {}
            for _, st, _, rid in region:
                if st:
                    states_by_region.setdefault(rid, set()).add(_norm(st))
            partitioned = {rid for rid, sts in states_by_region.items() if sts & platform_states}
            pool = [(sid, st, ct) for sid, st, ct, rid in region if rid not in partitioned or _norm(st) in mine]
        add_s, add_c = add_states_of.get(emp.id, set()), add_cities_of.get(emp.id, set())
        if add_s or add_c:       # places added by hand come on top, whatever the region partition says
            have = {sid for sid, _, _ in pool}
            pool += [(sid, st, ct) for sid, st, _, ct in live if sid not in have and (_norm(st) in add_s or _norm(ct) in add_c)]
        out[emp.id] = [sid for sid, st, ct in pool if _norm(st) not in ex_s and _norm(ct) not in ex_c]
    return out, all_ids
