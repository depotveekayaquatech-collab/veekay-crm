"""
Bottle-order marking. Core invariants (functional spec §21):
  - 0 is a real "marked" value; a missing row = not marked.
  - An employee marks a (store, date) exactly once; only an admin edits/clears after.
  - Only LIVE stores accept marks.
  - Data-hiding checks fail open; auth checks fail closed.
"""
from __future__ import annotations

import calendar as _calendar
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.audit_log import AuditLog
from sqlalchemy import exists
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.order_entry_repository import OrderEntryRepository
from app.schemas.order import (
    AdminEntryRequest,
    ScopeRow,
    StatusByPlatform,
    AttentionStore,
    CalendarDay,
    CoverageRow,
    DailyOverview,
    DashboardInsights,
    EmployeeOverviewRow,
    LeaderRow,
    MarkRequest,
    MyStore,
    OrderCalendar,
    PlatformSummary,
    SubmissionRow,
    TrendPoint,
)
from app.services import activity_service, assignment_service

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _store_meta(store: Store) -> dict:
    return {
        "store_name": store.name,
        "store_code": store.external_code,
        "state": store.state,
        "region": store.region.name if store.region else None,
        "partner_slug": store.partner_organization.slug if store.partner_organization else None,
    }


# --------------------------------------------------------------------------
# employee: my stores + calendar + mark
# --------------------------------------------------------------------------

def my_stores(db: Session, employee: User, *, is_admin: bool = False) -> list[MyStore]:
    today = _today()
    yesterday = today - timedelta(days=1)

    if is_admin:
        # Admins work with every live store: read plain columns instead of building ~1,500 ORM objects.
        rows = db.execute(
            select(
                Store.id, Store.name, Store.external_code, Store.state, Store.city, Region.name, Store.vendor_name,
                Store.vendor_number, Store.poc_name, Store.poc_number, Store.status, Organization.slug, Organization.name,
                Store.region_id,
            )
            .select_from(Store)
            .outerjoin(Region, Region.id == Store.region_id)
            .join(Organization, Organization.id == Store.partner_organization_id)
            .where(Store.organization_id == employee.organization_id, Store.status == StoreStatus.LIVE.value)
            .order_by(Store.name)
        ).all()
        counts = {
            (r[0], r[1]): int(r[2])
            for r in db.execute(
                select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count).where(
                    OrderEntry.organization_id == employee.organization_id, OrderEntry.order_date.in_([today, yesterday])
                )
            )
        }
        return [
            MyStore(
                id=r[0], name=r[1], external_code=r[2], state=r[3], city=r[4], region_name=r[5], vendor_name=r[6],
                vendor_number=r[7], poc_name=r[8], poc_number=r[9], status=r[10], today=today, partner_slug=r[11],
                partner_name=r[12], region_id=r[13], today_count=counts.get((r[0], today)),
                yesterday_count=counts.get((r[0], yesterday)),
            )
            for r in rows
        ]

    stores = assignment_service.visible_stores(db, employee)
    counts: dict[tuple[uuid.UUID, date], int] = {}
    if stores:
        rows = db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count).where(
                OrderEntry.store_id.in_([s.id for s in stores]),
                OrderEntry.order_date.in_([today, yesterday]),
            )
        )
        counts = {(r[0], r[1]): int(r[2]) for r in rows}
    return [
        MyStore(
            id=s.id, name=s.name, external_code=s.external_code, state=s.state, city=s.city,
            region_name=s.region.name if s.region else None,
            vendor_name=s.vendor_name, vendor_number=s.vendor_number,
            poc_name=s.poc_name, poc_number=s.poc_number,
            status=s.status, today=today,
            partner_slug=s.partner_organization.slug if s.partner_organization else None,
            partner_name=s.partner_organization.name if s.partner_organization else None,
            region_id=s.region_id,
            today_count=counts.get((s.id, today)), yesterday_count=counts.get((s.id, yesterday)),
        )
        for s in stores
    ]


def get_calendar(
    db: Session, user: User, store_id: uuid.UUID, year: int, month: int, *, is_admin: bool
) -> OrderCalendar:
    store = _resolve_store(db, user, store_id, is_admin=is_admin)
    repo = OrderEntryRepository(db)
    entries = repo.month_map(store.id, year, month)
    today = _today()
    days_in_month = _calendar.monthrange(year, month)[1]

    days: list[CalendarDay] = []
    for d in range(1, days_in_month + 1):
        the_date = date(year, month, d)
        entry = entries.get(d)
        days.append(
            CalendarDay(
                day=d,
                date=the_date,
                marked=entry is not None,
                count=entry.bottle_count if entry else None,
                source=entry.source if entry else None,
                is_today=(the_date == today),
                is_future=(the_date > today),
            )
        )

    return OrderCalendar(
        store_id=store.id,
        store_name=store.name,
        store_code=store.external_code,
        region_name=store.region.name if store.region else None,
        year=year,
        month=month,
        month_label=f"{_MONTHS[month]} {year}",
        days=days,
    )


def mark(db: Session, employee: User, payload: MarkRequest, *, is_admin: bool = False) -> OrderCalendar:
    if is_admin:
        # An admin needs nobody's sign-off: any store, any (non-future) date, and saved days can be changed.
        return admin_set_entry(
            db, employee, AdminEntryRequest(store_id=payload.store_id, order_date=payload.order_date, bottle_count=payload.bottle_count)
        )
    count = payload.bottle_count
    if not (settings.MIN_BOTTLE_COUNT <= count <= settings.MAX_BOTTLE_COUNT):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Bottle count must be a whole number from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}.",
        )

    visible = {s.id: s for s in assignment_service.visible_stores(db, employee)}
    store = visible.get(payload.store_id)
    if store is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
    if store.status != StoreStatus.LIVE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "This store is not currently live and cannot accept orders.")

    _check_order_date(payload.order_date)

    repo = OrderEntryRepository(db)
    existing = repo.get(store.id, payload.order_date)
    if existing is not None and existing.cash_adjustment != existing.bottle_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "This date is already marked and cannot be changed. Ask an admin to correct it.")
    if existing is not None:
        # The day only holds a developer adjustment so far (no real employee entry): the employee's count goes
        # underneath it and the adjustment stays on top.
        existing.bottle_count = count + existing.cash_adjustment
        existing.source = EntrySource.EMPLOYEE.value
        existing.marked_by_user_id = employee.id
    else:
        repo.add(OrderEntry(
            organization_id=employee.organization_id,
            store_id=store.id,
            order_date=payload.order_date,
            bottle_count=count,
            source=EntrySource.EMPLOYEE.value,
            marked_by_user_id=employee.id,
        ))
    activity_service.record(
        db, actor=employee, action="order.marked", entity_type="order_entry", entity_id=store.id,
        metadata={**_store_meta(store), "order_date": payload.order_date.isoformat(), "bottle_count": count},
    )
    db.commit()
    return get_calendar(db, employee, store.id, payload.order_date.year, payload.order_date.month, is_admin=False)


def admin_set_entry(db: Session, admin: User, payload: AdminEntryRequest) -> OrderCalendar:
    store = _resolve_store(db, admin, payload.store_id, is_admin=True)
    _check_order_date(payload.order_date, allow_any_month=True)
    repo = OrderEntryRepository(db)
    existing = repo.get(store.id, payload.order_date)

    if payload.bottle_count is None:
        if existing is not None:
            db.delete(existing)
            activity_service.record(
                db, actor=admin, action="order.cleared", entity_type="order_entry", entity_id=store.id,
                metadata={**_store_meta(store), "order_date": payload.order_date.isoformat(), "bottle_count": "CLEARED"},
            )
    else:
        if existing is not None:
            existing.bottle_count = payload.bottle_count
            existing.cash_adjustment = 0  # an explicit admin correction sets the final number
            existing.source = EntrySource.ADMIN.value
            existing.marked_by_user_id = admin.id
        else:
            repo.add(OrderEntry(
                organization_id=admin.organization_id,
                store_id=store.id,
                order_date=payload.order_date,
                bottle_count=payload.bottle_count,
                source=EntrySource.ADMIN.value,
                marked_by_user_id=admin.id,
            ))
        activity_service.record(
            db, actor=admin, action="order.corrected", entity_type="order_entry", entity_id=store.id,
            metadata={**_store_meta(store), "order_date": payload.order_date.isoformat(), "bottle_count": payload.bottle_count},
        )
    db.commit()
    return get_calendar(db, admin, store.id, payload.order_date.year, payload.order_date.month, is_admin=True)


# --------------------------------------------------------------------------
# admin: daily overview + submissions
# --------------------------------------------------------------------------

def _employee_rollups(
    db: Session, org_id: uuid.UUID, partner: Organization, target: date
) -> list[tuple[User, int, int, int]]:
    """[(employee, stores, entries_done, bottles)] for every employee of a platform on one day — a handful of
    queries in total, however many employees there are."""
    employees = EmployeeRepository(db).all_for_platform(org_id, partner.id)
    scopes, all_ids = assignment_service.employee_store_scopes(db, partner, employees)
    by_store = OrderEntryRepository(db).rollup_by_store(all_ids, target)
    out = []
    for emp in employees:
        ids = scopes.get(emp.id, [])
        done = sum(1 for sid in ids if sid in by_store)
        bottles = sum(by_store[sid][1] for sid in ids if sid in by_store)
        out.append((emp, len(ids), done, bottles))
    return out


def daily_overview(db: Session, admin: User, partner_slug: str, day_offset: int) -> DailyOverview:
    partner = db.execute(
        select(Organization).where(Organization.slug == partner_slug)
    ).scalar_one_or_none()
    if partner is None or partner.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{partner_slug} is not a configured platform.")

    day_offset = 1 if day_offset == 1 else 0
    target = _today() - timedelta(days=day_offset)
    repo = OrderEntryRepository(db)

    rows: list[EmployeeOverviewRow] = []
    for emp, total, done, bottles in _employee_rollups(db, admin.organization_id, partner, target):
        rows.append(EmployeeOverviewRow(
            employee_id=emp.id, employee_code=emp.employee_code, employee_name=emp.full_name,
            region_name=emp.region.name if emp.region else None,
            total_stores=total, entries_done=done, bottles=bottles,
            percent=round((done / total) * 100, 1) if total else 0.0,
        ))

    rows.sort(key=lambda r: r.employee_name.lower())

    try:
        subs = _recent(db, admin.organization_id, partner.id)
    except Exception:  # noqa: BLE001
        subs = []

    return DailyOverview(
        partner_slug=partner.slug,
        partner_label=partner.name,
        date=target,
        date_label="Yesterday" if day_offset == 1 else "Today",
        day_offset=day_offset,
        employees=rows,
        recent_submissions=subs,
    )


def _recent(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID) -> list[SubmissionRow]:
    out = []
    for entry, name, store_name, store_code in OrderEntryRepository(db).recent_for_partner(org_id, partner_id, 50):
        out.append(SubmissionRow(
            id=entry.id,
            submitted_at=entry.updated_at,
            employee_name=(f"{name} (ADMIN)" if entry.source == EntrySource.ADMIN.value and name else name),
            source=entry.source,
            store_code=store_code,
            store_name=store_name,
            order_date=entry.order_date,
            bottle_count=entry.bottle_count,
        ))
    return out


# --------------------------------------------------------------------------
# admin: dashboard insights (charts)
# --------------------------------------------------------------------------

def dashboard_insights(db: Session, admin: User, days: int = 14) -> DashboardInsights:
    org_id = admin.organization_id
    today = _today()
    repo = OrderEntryRepository(db)

    # --- trend: last `days` days, org-wide ---
    start = today - timedelta(days=days - 1)
    totals = repo.daily_totals_between(org_id, start, today)
    trend: list[TrendPoint] = []
    for i in range(days):
        d = start + timedelta(days=i)
        entries, bottles = totals.get(d, (0, 0))
        trend.append(TrendPoint(
            date=d, label=f"{d.strftime('%a')} {d.day}", entries=entries, bottles=bottles,
        ))

    # --- store status breakdown ---
    status_rows = db.execute(
        select(Store.status, func.count(Store.id))
        .where(Store.organization_id == org_id)
        .group_by(Store.status)
    ).all()
    store_status = {s.value: 0 for s in StoreStatus}
    for value, count in status_rows:
        store_status[value] = int(count)

    # --- per-platform status counts (one grouped query; replaces shipping every store to the browser) ---
    plat_rows = db.execute(
        select(Organization.id, Organization.slug, Organization.name, Store.status, func.count(Store.id))
        .select_from(Store)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .where(Store.organization_id == org_id)
        .group_by(Organization.id, Organization.slug, Organization.name, Store.status)
        .order_by(Organization.name)
    ).all()
    by_platform: dict[uuid.UUID, dict] = {}
    for pid, slug, label, st, n in plat_rows:
        d = by_platform.setdefault(pid, {"slug": slug, "label": label, "LIVE": 0, "PENDING": 0, "CLOSE": 0})
        d[st] = int(n)
    status_by_platform = [
        StatusByPlatform(slug=d["slug"], label=d["label"], live=d["LIVE"], pending=d["PENDING"], close=d["CLOSE"],
                         total=d["LIVE"] + d["PENDING"] + d["CLOSE"])
        for d in by_platform.values()
    ]

    # --- (platform, region, state) combinations, for the linked filter dropdowns ---
    scopes = [
        ScopeRow(partner_slug=r[0], region=r[1], state=r[2])
        for r in db.execute(
            select(Organization.slug, Region.name, Store.state)
            .select_from(Store)
            .join(Organization, Organization.id == Store.partner_organization_id)
            .outerjoin(Region, Region.id == Store.region_id)
            .where(Store.organization_id == org_id)
            .group_by(Organization.slug, Region.name, Store.state)
            .order_by(Organization.slug, Region.name, Store.state)
        ).all()
    ]

    # --- stores that need attention: not live yet (50 at most) ---
    attention_stores = [
        AttentionStore(
            id=r[0], name=r[1], external_code=r[2], platform=r[3], status=r[4], city=r[5], state=r[6], region_name=r[7]
        )
        for r in db.execute(
            select(Store.id, Store.name, Store.external_code, Organization.name, Store.status, Store.city, Store.state, Region.name)
            .select_from(Store)
            .join(Organization, Organization.id == Store.partner_organization_id)
            .outerjoin(Region, Region.id == Store.region_id)
            .where(Store.organization_id == org_id, Store.status != StoreStatus.LIVE.value)
            .order_by(Store.status, Store.name)
            .limit(50)
        ).all()
    ]

    # --- live stores with no order in the last 30 days ---
    recent = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date >= today - timedelta(days=29))
    dormant_where = (Store.organization_id == org_id, Store.status == StoreStatus.LIVE.value, ~recent)
    dormant_live = int(db.execute(select(func.count(Store.id)).where(*dormant_where)).scalar_one())
    dormant_stores = [
        AttentionStore(
            id=r[0], name=r[1], external_code=r[2], platform=r[3], status=r[4], city=r[5], state=r[6], region_name=r[7]
        )
        for r in db.execute(
            select(Store.id, Store.name, Store.external_code, Organization.name, Store.status, Store.city, Store.state, Region.name)
            .select_from(Store)
            .join(Organization, Organization.id == Store.partner_organization_id)
            .outerjoin(Region, Region.id == Store.region_id)
            .where(*dormant_where)
            .order_by(Store.name)
            .limit(24)
        ).all()
    ] if dormant_live else []

    # --- per-platform today summary + leaderboard (bulk: no per-employee queries) ---
    partners = db.execute(
        select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value)
    ).scalars().all()

    platforms: list[PlatformSummary] = []
    leaderboard: list[LeaderRow] = []
    for partner in partners:
        p_total = p_done = p_bottles = p_emps = 0
        for emp, total, done, bottles in _employee_rollups(db, org_id, partner, today):
            p_emps += 1
            p_total += total
            p_done += done
            p_bottles += bottles
            leaderboard.append(LeaderRow(
                employee_name=emp.full_name,
                region_name=emp.region.name if emp.region else None,
                entries_done=done, total_stores=total, bottles=bottles,
                percent=round((done / total) * 100, 1) if total else 0.0,
            ))
        counts = by_platform.get(partner.id, {"LIVE": 0, "PENDING": 0, "CLOSE": 0})
        platforms.append(PlatformSummary(
            slug=partner.slug, label=partner.name,
            total_stores=p_total, entries_done=p_done, bottles=p_bottles,
            percent=round((p_done / p_total) * 100, 1) if p_total else 0.0,
            employees=p_emps,
            all_stores=counts["LIVE"] + counts["PENDING"] + counts["CLOSE"],
            live_stores=counts["LIVE"],
        ))

    leaderboard.sort(key=lambda r: (r.bottles, r.entries_done), reverse=True)

    e_today, b_today = totals.get(today, (0, 0))
    _, b_yesterday = totals.get(today - timedelta(days=1), (0, 0))

    # --- store coverage ---
    live_case = func.sum(case((Store.status == StoreStatus.LIVE.value, 1), else_=0))
    region_rows = db.execute(
        select(Region.name, live_case, func.count(Store.id))
        .select_from(Store)
        .outerjoin(Region, Region.id == Store.region_id)
        .where(Store.organization_id == org_id)
        .group_by(Region.name)
        .order_by(func.count(Store.id).desc())
    ).all()
    stores_by_region = [
        CoverageRow(label=r[0] or "Unassigned", live=int(r[1] or 0), total=int(r[2]))
        for r in region_rows
    ]

    state_rows = db.execute(
        select(Store.state, live_case, func.count(Store.id))
        .where(Store.organization_id == org_id)
        .group_by(Store.state)
        .order_by(func.count(Store.id).desc())
        .limit(12)
    ).all()
    stores_by_state = [
        CoverageRow(label=r[0] or "—", live=int(r[1] or 0), total=int(r[2]))
        for r in state_rows
    ]

    last_store_sync = db.execute(
        select(func.max(AuditLog.created_at)).where(
            AuditLog.organization_id == org_id, AuditLog.action == "store.synced"
        )
    ).scalar_one_or_none()

    return DashboardInsights(
        trend=trend,
        store_status=store_status,
        platforms=platforms,
        leaderboard=leaderboard[:5],
        bottles_today=b_today,
        bottles_yesterday=b_yesterday,
        entries_today=e_today,
        stores_by_region=stores_by_region,
        stores_by_state=stores_by_state,
        attention_stores=attention_stores,
        status_by_platform=status_by_platform,
        scopes=scopes,
        dormant_live=dormant_live,
        dormant_stores=dormant_stores,
        last_store_sync=last_store_sync,
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _resolve_store(db: Session, user: User, store_id: uuid.UUID, *, is_admin: bool) -> Store:
    store = OrderEntryRepository(db).store_with_meta(user.organization_id, store_id)
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    if not is_admin:
        if store_id not in assignment_service.visible_store_ids(db, user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
    return store


def _check_order_date(order_date: date, *, allow_any_month: bool = False) -> None:
    today = _today()
    if order_date > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You can't mark a future date.")
    if not allow_any_month and (order_date.year, order_date.month) != (today.year, today.month):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Orders can only be marked for dates in the current month.",
        )
