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
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.order_entry_repository import OrderEntryRepository
from app.schemas.order import (
    AdminEntryRequest,
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

def my_stores(db: Session, employee: User) -> list[MyStore]:
    return [
        MyStore(
            id=s.id, name=s.name, external_code=s.external_code, state=s.state, city=s.city,
            region_name=s.region.name if s.region else None,
            vendor_name=s.vendor_name, vendor_number=s.vendor_number,
            poc_name=s.poc_name, poc_number=s.poc_number,
        )
        for s in assignment_service.visible_stores(db, employee)
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


def mark(db: Session, employee: User, payload: MarkRequest) -> OrderCalendar:
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
    if repo.get(store.id, payload.order_date) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This date is already marked and cannot be changed. Ask an admin to correct it.")

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
    for emp in EmployeeRepository(db).all_for_platform(admin.organization_id, partner.id):
        try:
            stores = assignment_service.visible_stores(db, emp)
            total = len(stores)
            done, bottles = repo.rollup_for_date([s.id for s in stores], target)
            pct = round((done / total) * 100, 1) if total else 0.0
            rows.append(EmployeeOverviewRow(
                employee_id=emp.id, employee_code=emp.employee_code, employee_name=emp.full_name,
                region_name=emp.region.name if emp.region else None,
                total_stores=total, entries_done=done, bottles=bottles, percent=pct,
            ))
        except Exception as exc:  # noqa: BLE001 — one bad employee must not blank the table
            rows.append(EmployeeOverviewRow(
                employee_id=emp.id, employee_code=emp.employee_code, employee_name=emp.full_name,
                region_name=None, total_stores=0, entries_done=0, bottles=0, percent=0.0,
                error=str(exc),
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

    # --- every store, both platforms (same rows as the Stores page / Sheet sync) ---
    all_store_rows = db.execute(
        select(Store)
        .where(Store.organization_id == org_id)
        .options(joinedload(Store.region), joinedload(Store.partner_organization))
        .order_by(Store.name)
    ).unique().scalars().all()

    def _to_row(s: Store) -> AttentionStore:
        return AttentionStore(
            id=s.id, name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            status=s.status, city=s.city, state=s.state,
            region_name=s.region.name if s.region else None,
        )

    all_stores = [_to_row(s) for s in all_store_rows]
    attention_stores = [
        _to_row(s)
        for s in sorted(all_store_rows, key=lambda s: (s.status, s.name))
        if s.status != StoreStatus.LIVE.value
    ][:50]

    # --- per-platform today summary + leaderboard ---
    partners = db.execute(
        select(Organization).where(
            Organization.kind == OrganizationKind.PARTNER.value
        )
    ).scalars().all()

    platforms: list[PlatformSummary] = []
    leaderboard: list[LeaderRow] = []
    for partner in partners:
        p_total = p_done = p_bottles = p_emps = 0
        for emp in EmployeeRepository(db).all_for_platform(org_id, partner.id):
            p_emps += 1
            try:
                stores = assignment_service.visible_stores(db, emp)
            except Exception:  # noqa: BLE001
                continue
            total = len(stores)
            done, bottles = repo.rollup_for_date([s.id for s in stores], today)
            p_total += total
            p_done += done
            p_bottles += bottles
            leaderboard.append(LeaderRow(
                employee_name=emp.full_name,
                region_name=emp.region.name if emp.region else None,
                entries_done=done, total_stores=total, bottles=bottles,
                percent=round((done / total) * 100, 1) if total else 0.0,
            ))
        p_all = [s for s in all_store_rows if s.partner_organization_id == partner.id]
        platforms.append(PlatformSummary(
            slug=partner.slug, label=partner.name,
            total_stores=p_total, entries_done=p_done, bottles=p_bottles,
            percent=round((p_done / p_total) * 100, 1) if p_total else 0.0,
            employees=p_emps,
            all_stores=len(p_all),
            live_stores=sum(1 for s in p_all if s.status == StoreStatus.LIVE.value),
        ))

    leaderboard.sort(key=lambda r: (r.bottles, r.entries_done), reverse=True)

    e_today, b_today = totals.get(today, (0, 0))
    _, b_yesterday = totals.get(today - timedelta(days=1), (0, 0))

    # --- store coverage: same `stores` rows the Stores page / sync use ---
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
        all_stores=all_stores,
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
