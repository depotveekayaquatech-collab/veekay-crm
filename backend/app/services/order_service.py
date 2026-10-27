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
from sqlalchemy import literal_column, case, func, select
from sqlalchemy.exc import IntegrityError
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
    MarkManyRequest,
    MarkManyResult,
    MarkRequest,
    MarkResultItem,
    MyStore,
    OrderCalendar,
    PlatformSummary,
    SubmissionRow,
    TrendPoint,
)
from app.core import audit_context
from app.core.entry_access import ROLE_RANK, EntryScope, owned_clause, owns_value, sees_every_entry, set_by_someone_above, viewer_rank, visible_clause
from app.services import activity_service, assignment_service, order_journal_service, vendor_history_service
from app.services.entry_changes import last_changes, last_changes_for, status_for_contributor

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

def _month_totals(db: Session, ids: list[uuid.UUID], today: date, *, net: bool, owner: uuid.UUID | None = None, rank: int = 1) -> dict[uuid.UUID, tuple[int, int, int]]:
    """{store_id: (bottles marked this month so far, bottles marked in the whole of last month, days of last month with an entry)}. `net` leaves out a developer's cash
    adjustment, which an employee never sees (what they entered is what they are shown)."""
    if not ids:
        return {}
    this_start = today.replace(day=1)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    amount = (OrderEntry.bottle_count - OrderEntry.cash_adjustment) if net else OrderEntry.bottle_count
    if owner:
        amount = case((visible_clause({owner}, rank), amount), else_=0)      # bottle totals: your own numbers plus those set by someone more senior; never a peer's. The day count below stays everyone's
    rows = db.execute(
        select(
            OrderEntry.store_id,
            func.coalesce(func.sum(case((OrderEntry.order_date >= this_start, amount), else_=0)), 0),
            func.coalesce(func.sum(case((OrderEntry.order_date < this_start, amount), else_=0)), 0),
            func.coalesce(func.sum(case((OrderEntry.order_date < this_start, 1), else_=0)), 0),
        )
        .where(OrderEntry.store_id.in_(ids), OrderEntry.order_date >= last_start, OrderEntry.order_date <= today)
        .group_by(OrderEntry.store_id)
    ).all()
    return {r[0]: (int(r[1]), int(r[2]), int(r[3])) for r in rows}


def _last_month_missing(entries: int, start: date | None, today: date) -> int:
    """Days of last month (from the store's start date, if later) that still have no entry."""
    last_end = today.replace(day=1) - timedelta(days=1)
    first = max(last_end.replace(day=1), start) if start else last_end.replace(day=1)
    return 0 if first > last_end else max(0, (last_end - first).days + 1 - entries)


def _twin_names(db: Session, org_id: uuid.UUID) -> set[tuple[str, str]]:
    """{(platform slug, normalised name)} of every name that two or more stores of one platform share."""
    rows = db.execute(
        select(Organization.slug, func.lower(func.regexp_replace(func.btrim(Store.name), r"\s+", " ", "g")))
        .select_from(Store).join(Organization, Organization.id == Store.partner_organization_id)
        .where(Store.organization_id == org_id)
        .group_by(literal_column("1"), literal_column("2"))          # by position: the same expression with fresh bind parameters would not match
        .having(func.count(Store.id) > 1)
    ).all()
    return {(r[0], r[1]) for r in rows}


def _name_key(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def my_stores(db: Session, employee: User, *, is_admin: bool = False) -> list[MyStore]:
    from app.services import inventory_service

    twins = _twin_names(db, employee.organization_id)

    def _month_stats(ids: list[uuid.UUID], day: date) -> dict:
        return inventory_service.month_stats(db, ids, day)

    def _pending(stats: dict, sid: uuid.UUID, day: date, start: date | None) -> int:
        # a store that has not started yet, or has no live status, is never "behind"; the same rule as the Inventory page
        return inventory_service.pending_days(stats.get(sid, (None,))[0], day, start)

    today = _today()
    yesterday = today - timedelta(days=1)
    until = backmonth_open_until(today)
    window = until if until is not None and today <= until else None     # last month can still be marked

    def _last_missing(totals: dict, sid: uuid.UUID, start: date | None) -> int:
        return _last_month_missing(totals.get(sid, (0, 0, 0))[2], start, today) if window else 0

    if is_admin:
        # Admins work with every live store: read plain columns instead of building ~1,500 ORM objects.
        rows = db.execute(
            select(
                Store.id, Store.name, Store.external_code, Store.state, Store.city, Region.name, Store.vendor_name,
                Store.vendor_number, Store.poc_name, Store.poc_number, Store.status, Organization.slug, Organization.name,
                Store.region_id, Store.start_date, Store.crm_code,
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
        stats = _month_stats([r[0] for r in rows], today)
        totals = _month_totals(db, [r[0] for r in rows], today, net=False)
        return [
            MyStore(
                id=r[0], name=r[1], external_code=r[2], crm_code=r[15], duplicate_name=(r[11], _name_key(r[1])) in twins,
                state=r[3], city=r[4], region_name=r[5], vendor_name=r[6],
                vendor_number=r[7], poc_name=r[8], poc_number=r[9], status=r[10], today=today, partner_slug=r[11],
                partner_name=r[12], region_id=r[13], today_count=counts.get((r[0], today)),
                yesterday_count=counts.get((r[0], yesterday)),
                today_marked=(r[0], today) in counts, yesterday_marked=(r[0], yesterday) in counts, pending_days=_pending(stats, r[0], today, r[14]),
                month_bottles=totals.get(r[0], (0, 0, 0))[0], last_month_bottles=totals.get(r[0], (0, 0, 0))[1],
                last_month_missing=_last_missing(totals, r[0], r[14]), last_month_open_until=window,
            )
            for r in rows
        ]

    stores = assignment_service.visible_stores(db, employee)
    my_rank = viewer_rank(db, employee)
    sees_all = sees_every_entry(db, employee)              # every Level 1 employee: colleagues' numbers too, read-only
    counts: dict[tuple[uuid.UUID, date], int] = {}         # the numbers you may see: yours, those of colleagues, and those set by someone more senior
    marked_days: set[tuple[uuid.UUID, date]] = set()       # days anybody marked (a state, not a number)
    edited: dict[tuple[uuid.UUID, date], tuple[uuid.UUID, int]] = {}   # the numbers you may see that somebody changed after they were entered: (entry id, cash adjustment)
    if stores:
        rows = db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count, OrderEntry.cash_adjustment, OrderEntry.created_by_user_id,
                   OrderEntry.source, OrderEntry.marked_by_user_id, OrderEntry.last_modified_by_user_id, OrderEntry.last_modified_at,
                   OrderEntry.last_modified_by_role, OrderEntry.created_by_role, OrderEntry.creator_verified, OrderEntry.id, OrderEntry.version).where(
                OrderEntry.store_id.in_([s.id for s in stores]),
                OrderEntry.order_date.in_([today, yesterday]),
            )
        )
        for r in rows:
            marked_days.add((r[0], r[1]))
            above = int(r[3]) == 0 and (
                (ROLE_RANK.get((r[9] if r[8] is not None else r[10]) or "", 0) > my_rank)
                or (my_rank < 4 and not r[11] and r[8] is None and r[5] == "admin")
            )
            if (sees_all and (int(r[3]) == 0 or r[5] == "employee")) or r[4] == employee.id or (r[5] == "employee" and r[6] == employee.id and r[7] == employee.id) or above:
                counts[(r[0], r[1])] = int(r[2]) - int(r[3])
                if r[13] and r[13] > 1:
                    edited[(r[0], r[1])] = (r[12], int(r[3]))
    changes = last_changes_for(db, {eid: adj for eid, adj in edited.values()})
    stats = _month_stats([s.id for s in stores], today)
    totals = _month_totals(db, [s.id for s in stores], today, net=True, owner=None if sees_all else employee.id, rank=my_rank)
    return [
        MyStore(
            id=s.id, name=s.name, external_code=s.external_code, crm_code=s.crm_code,
            duplicate_name=((s.partner_organization.slug if s.partner_organization else ""), _name_key(s.name)) in twins,
            state=s.state, city=s.city,
            region_name=s.region.name if s.region else None,
            vendor_name=s.vendor_name, vendor_number=s.vendor_number,
            poc_name=s.poc_name, poc_number=s.poc_number,
            status=s.status, today=today,
            partner_slug=s.partner_organization.slug if s.partner_organization else None,
            partner_name=s.partner_organization.name if s.partner_organization else None,
            region_id=s.region_id,
            today_count=counts.get((s.id, today)), yesterday_count=counts.get((s.id, yesterday)),
            today_changed=changes.get(edited.get((s.id, today), (None, 0))[0]), yesterday_changed=changes.get(edited.get((s.id, yesterday), (None, 0))[0]),
            today_marked=(s.id, today) in marked_days, yesterday_marked=(s.id, yesterday) in marked_days,
            pending_days=_pending(stats, s.id, today, s.start_date),
            month_bottles=totals.get(s.id, (0, 0, 0))[0], last_month_bottles=totals.get(s.id, (0, 0, 0))[1],
            last_month_missing=_last_missing(totals, s.id, s.start_date), last_month_open_until=window,
        )
        for s in stores
    ]


def get_calendar(
    db: Session, user: User, store_id: uuid.UUID, year: int, month: int, *, is_admin: bool, scope: "EntryScope | None" = None
) -> OrderCalendar:
    store = _resolve_store(db, user, store_id, is_admin=is_admin)
    rank = viewer_rank(db, user)
    sees_all = not is_admin and sees_every_entry(db, user)       # entries.view_all: read-only, every entry of a store they can reach
    repo = OrderEntryRepository(db)
    entries = repo.month_map(store.id, year, month)
    who = {
        r[0]: r[1] for r in db.execute(
            select(User.id, User.full_name).where(User.id.in_({e.marked_by_user_id for e in entries.values() if e.marked_by_user_id}))
        )
    } if entries else {}
    today = _today()
    days_in_month = _calendar.monthrange(year, month)[1]

    # Who may see which day (An Entry Contributor sees only the numbers THEY entered; `scope` widens it for a Team Lead / reviewer).
    seen: dict[int, tuple[bool, bool, bool, bool]] = {}
    for d, entry in entries.items():
        mine = entry.created_by_user_id == user.id or (
            entry.source == EntrySource.EMPLOYEE.value and entry.marked_by_user_id == user.id and entry.last_modified_by_user_id == user.id)
        # a colleague's number is shown, but never a day that holds only a developer's cash adjustment
        peer_visible = sees_all and (not entry.cash_adjustment or entry.source == EntrySource.EMPLOYEE.value)
        in_scope = scope is not None and (scope.creator_ids is None or owns_value(entry, scope.creator_ids))
        above = not is_admin and set_by_someone_above(entry, rank)       # a more senior person set it: visible, read-only
        seen[d] = (mine, in_scope, above, is_admin or mine or in_scope or above or peer_visible)
    # What happened to the numbers the caller can see after they were entered: who changed it (name + role), when, old -> new, and the verification state.
    visible_entries = [entries[d] for d, v in seen.items() if v[3]]
    changes = last_changes(db, visible_entries)
    state_names = {
        r[0]: r[1] for r in db.execute(select(User.id, User.full_name).where(User.id.in_(
            {i for e in visible_entries for i in (e.verified_by_user_id, e.l3_reviewed_by_user_id) if i}))
        )
    } if visible_entries else {}

    days: list[CalendarDay] = []
    for d in range(1, days_in_month + 1):
        the_date = date(year, month, d)
        entry = entries.get(d)
        # A day somebody else marked still shows as marked (so it cannot be marked twice) but carries no count, name or time.
        # Administrators see everything, with who created it and its version.
        mine, in_scope, above, shown = seen[d] if entry is not None else (False, False, False, False)
        days.append(
            CalendarDay(
                day=d,
                date=the_date,
                marked=entry is not None,
                count=(entry.bottle_count if is_admin else entry.bottle_count - entry.cash_adjustment) if shown else None,
                source=(entry.source if shown else "other") if entry else None,
                entered_by=who.get(entry.marked_by_user_id) if shown else None,
                entered_at=(entry.updated_at or entry.created_at) if shown else None,
                is_today=(the_date == today),
                is_future=(the_date > today),
                mine=mine, masked=entry is not None and not shown, by_higher=bool(above and not mine and not in_scope),
                entry_id=entry.id if (entry and is_admin) else None, version=entry.version if (entry and is_admin) else None,
                creator_name=(entry.created_by_name if entry.creator_verified else None) if (entry and is_admin) else None,
                creator_verified=entry.creator_verified if (entry and is_admin) else None,
                verification=status_for_contributor(entry, state_names) if (entry and shown) else None,
                changed=changes.get(entry.id) if (entry and shown) else None,
            )
        )

    return OrderCalendar(
        store_id=store.id,
        store_name=store.name,
        store_crm_code=store.crm_code,
        store_code=store.external_code,
        region_name=store.region.name if store.region else None,
        year=year,
        month=month,
        month_label=f"{_MONTHS[month]} {year}",
        days=days,
        can_mark=is_admin or employee_can_mark_month(year, month, today),
        open_until=None if is_admin or (year, month) == (today.year, today.month) else backmonth_open_until(today),
    )


def _journal(db: Session, employee: User, store_id: uuid.UUID, rows: list[tuple[date, int | None, str, str | None, str | None]], *, action: str = "mark") -> None:
    """Write the attempts to the immutable mark journal (own connection, never raises). rows = (date, count, outcome, reason, request_key)."""
    order_journal_service.record_many([
        (employee.organization_id, employee.id, store_id, d, c, outcome, reason, action, key, audit_context.current_client(db))
        for (d, c, outcome, reason, key) in rows
    ])


def _entry_key(key: str | None, day: date) -> str | None:
    """The idempotency key of ONE entry: the submission's key plus its date, so a retried batch lines up entry by entry."""
    return f"{key.strip()[:100]}:{day.isoformat()}" if key and key.strip() else None


def mark(db: Session, employee: User, payload: MarkRequest, *, is_admin: bool = False, request_key: str | None = None, client_time: str | None = None) -> OrderCalendar:
    if is_admin:
        # An admin needs nobody's sign-off: any store, any (non-future) date, and saved days can be changed.
        return admin_set_entry(
            db, employee, AdminEntryRequest(store_id=payload.store_id, order_date=payload.order_date, bottle_count=payload.bottle_count)
        )
    count = payload.bottle_count
    key = _entry_key(request_key, payload.order_date)
    try:
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
        audit_context.bind(db, client_time=client_time)
        try:
            outcome = _write_employee_entry(db, employee, store, payload.order_date, count, key)
            db.commit()
        except IntegrityError:                       # two requests for the same store and day at once: the other won, so answer from its row
            db.rollback()
            audit_context.bind(db, client_time=client_time)
            outcome = _write_employee_entry(db, employee, store, payload.order_date, count, key)
            db.commit()
    except HTTPException as exc:
        db.rollback()
        _journal(db, employee, payload.store_id, [(payload.order_date, count, "rejected", str(exc.detail), key)])
        raise
    _journal(db, employee, store.id, [(payload.order_date, count, "saved" if outcome == "created" else "duplicate", None if outcome == "created" else "same number sent again", key)])
    return get_calendar(db, employee, store.id, payload.order_date.year, payload.order_date.month, is_admin=False)


def _write_employee_entry(db: Session, employee: User, store: Store, order_date: date, count: int, request_key: str | None = None) -> str:
    """One employee entry for one store and date (does not commit). Returns "created", or "replayed" when this same person already saved this same number
    (a lost response, a double tap, a retry after a timeout): nothing is written twice. 409 if the date is already marked by anyone else."""
    repo = OrderEntryRepository(db)
    existing = repo.get(store.id, order_date)
    if existing is not None:
        mine = existing.created_by_user_id == employee.id or (existing.marked_by_user_id == employee.id and existing.last_modified_by_user_id == employee.id)
        same_key = bool(request_key) and existing.request_id == request_key
        same_number = existing.source == EntrySource.EMPLOYEE.value and existing.bottle_count - existing.cash_adjustment == count
        if mine and (same_key or same_number):
            return "replayed"
    if existing is not None and existing.cash_adjustment != existing.bottle_count:
        raise HTTPException(status.HTTP_409_CONFLICT, "This date is already marked and cannot be changed. Ask your Team Lead or an admin to correct it.")
    audit_context.bind(db, request_key=request_key)
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
            order_date=order_date,
            bottle_count=count,
            source=EntrySource.EMPLOYEE.value,
            marked_by_user_id=employee.id,
        ))
    vendor_history_service.pull_start_back(db, store, order_date, count)
    activity_service.record(
        db, actor=employee, action="order.marked", entity_type="order_entry", entity_id=store.id,
        metadata={**_store_meta(store), "order_date": order_date.isoformat(), "bottle_count": count},
    )
    return "created"


def correct_own_entry(db: Session, employee: User, payload: AdminEntryRequest) -> OrderCalendar:
    """An employee changes (or clears, with no count) an entry THEY marked themselves, in the dates they can still mark. Anyone else's entry,
    and a day that holds only a developer adjustment, stays an admin's job. Every change is logged with what was there before."""
    if not settings.EMPLOYEE_CAN_CORRECT_OWN:
        _journal(db, employee, payload.store_id, [(payload.order_date, payload.bottle_count, "rejected", "employees cannot change a submitted entry", None)], action="correct")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A submitted entry can't be changed by the person who entered it. Ask your Team Lead or an admin to correct it.",
        )
    store = {s.id: s for s in assignment_service.visible_stores(db, employee)}.get(payload.store_id)
    if store is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
    if store.status != StoreStatus.LIVE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "This store is not currently live and cannot accept orders.")
    _check_order_date(payload.order_date)
    repo = OrderEntryRepository(db)
    existing = repo.get(store.id, payload.order_date)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no entry on this date to correct. Mark it instead.")
    if existing.cash_adjustment == existing.bottle_count or existing.created_by_user_id != employee.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only correct entries you marked yourself. Ask an admin to correct this one.")
    mine = existing.bottle_count - existing.cash_adjustment            # the employee's own part (a developer adjustment may sit on top)
    new = payload.bottle_count
    if new is not None and new == mine:
        return get_calendar(db, employee, store.id, payload.order_date.year, payload.order_date.month, is_admin=False)
    if new is not None and not (settings.MIN_BOTTLE_COUNT <= new <= settings.MAX_BOTTLE_COUNT):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Bottle count must be a whole number from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}.",
        )
    meta = {**_store_meta(store), "order_date": payload.order_date.isoformat(), "previous_count": mine}
    if new is None:
        if existing.cash_adjustment:
            existing.bottle_count = existing.cash_adjustment            # only the adjustment is left
            existing.marked_by_user_id = None
        else:
            db.delete(existing)                                          # the deleted-rows archive keeps a copy
        activity_service.record(db, actor=employee, action="order.cleared_by_employee", entity_type="order_entry", entity_id=store.id, metadata=meta)
    else:
        existing.bottle_count = new + existing.cash_adjustment
        activity_service.record(db, actor=employee, action="order.corrected_by_employee", entity_type="order_entry", entity_id=store.id, metadata={**meta, "bottle_count": new})
    db.commit()
    return get_calendar(db, employee, store.id, payload.order_date.year, payload.order_date.month, is_admin=False)


def mark_many(
    db: Session, employee: User, payload: MarkManyRequest, *, is_admin: bool = False, request_key: str | None = None, client_time: str | None = None,
) -> MarkManyResult:
    """Marks several dates of one store. The store is checked once (a wrong store fails the whole request); every date
    is then checked and saved on its own, so one bad date (already marked, future, other month) never blocks the rest.
    Each saved date comes back with the entry id, version and server time: that is the server's confirmation, the only thing the app may call "saved"."""
    days = [e.order_date for e in payload.entries]
    if len(set(days)) != len(days):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A date appears more than once.")
    results: list[MarkResultItem] = []
    if is_admin:
        for e in payload.entries:
            try:
                admin_set_entry(db, employee, AdminEntryRequest(store_id=payload.store_id, order_date=e.order_date, bottle_count=e.bottle_count))
                results.append(MarkResultItem(order_date=e.order_date, ok=True, status="saved"))
            except HTTPException as exc:
                db.rollback()
                results.append(MarkResultItem(order_date=e.order_date, ok=False, error=str(exc.detail)))
    else:
        try:
            store = {s.id: s for s in assignment_service.visible_stores(db, employee)}.get(payload.store_id)
            if store is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "This store is not assigned to you.")
            if store.status != StoreStatus.LIVE.value:
                raise HTTPException(status.HTTP_409_CONFLICT, "This store is not currently live and cannot accept orders.")
        except HTTPException as exc:
            _journal(db, employee, payload.store_id, [(e.order_date, e.bottle_count, "rejected", str(exc.detail), _entry_key(request_key, e.order_date)) for e in payload.entries])
            raise
        audit_context.bind(db, client_time=client_time)
        outcomes: dict[date, str] = {}
        journal_rows: list[tuple[date, int | None, str, str | None, str | None]] = []
        for e in sorted(payload.entries, key=lambda x: x.order_date):
            key = _entry_key(request_key, e.order_date)
            try:
                if not (settings.MIN_BOTTLE_COUNT <= e.bottle_count <= settings.MAX_BOTTLE_COUNT):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Bottle count must be a whole number from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}.",
                    )
                _check_order_date(e.order_date)
                try:
                    with db.begin_nested():
                        outcomes[e.order_date] = _write_employee_entry(db, employee, store, e.order_date, e.bottle_count, key)
                except IntegrityError:
                    # two requests for the same store and day at once: the other one won. The retry sees its row and answers properly.
                    with db.begin_nested():
                        outcomes[e.order_date] = _write_employee_entry(db, employee, store, e.order_date, e.bottle_count, key)
                results.append(MarkResultItem(order_date=e.order_date, ok=True))
            except HTTPException as exc:
                results.append(MarkResultItem(order_date=e.order_date, ok=False, error=str(exc.detail)))
                journal_rows.append((e.order_date, e.bottle_count, "rejected", str(exc.detail), key))
        db.commit()
        # The server's confirmation for each saved day: read back from the committed rows.
        if outcomes:
            rows = {r.order_date: r for r in db.execute(
                select(OrderEntry).where(OrderEntry.store_id == store.id, OrderEntry.order_date.in_(list(outcomes)))).scalars()}
            for r in results:
                row = rows.get(r.order_date)
                if r.ok and row is not None:
                    r.status = "saved" if outcomes[r.order_date] == "created" else "already_saved"
                    r.entry_id, r.saved_at, r.version = row.id, row.created_at, row.version
        counts = {e.order_date: e.bottle_count for e in payload.entries}
        journal_rows += [(d, counts[d], "saved" if o == "created" else "duplicate", None if o == "created" else "same number sent again", _entry_key(request_key, d))
                         for d, o in outcomes.items()]
        _journal(db, employee, store.id, journal_rows)
    saved = sum(1 for r in results if r.ok)
    return MarkManyResult(saved=saved, failed=len(results) - saved, results=results)


def admin_set_entry(db: Session, admin: User, payload: AdminEntryRequest) -> OrderCalendar:
    store = _resolve_store(db, admin, payload.store_id, is_admin=True)
    _check_order_date(payload.order_date, allow_any_month=True)
    repo = OrderEntryRepository(db)
    existing = repo.get(store.id, payload.order_date)

    if payload.bottle_count is None:
        if existing is not None:
            # the database keeps a copy of every deleted entry (deleted_rows, see migration 0043); the log says what was there
            was = {"previous_count": existing.bottle_count, "previous_cash_adjustment": existing.cash_adjustment, "previous_source": existing.source}
            db.delete(existing)
            activity_service.record(
                db, actor=admin, action="order.cleared", entity_type="order_entry", entity_id=store.id,
                metadata={**_store_meta(store), "order_date": payload.order_date.isoformat(), "bottle_count": "CLEARED", **was},
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
        vendor_history_service.pull_start_back(db, store, payload.order_date, payload.bottle_count)
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

def dashboard_insights(db: Session, admin: User, days: int = 14, partner_slug: str | None = None) -> DashboardInsights:
    """The dashboard numbers. With `partner_slug` EVERYTHING is for that one platform (Blinkit and Zepto are never added together);
    without it the legacy organisation-wide view is returned."""
    org_id = admin.organization_id
    pid = None
    if partner_slug:
        pid = db.execute(
            select(Organization.id).where(Organization.slug == partner_slug.strip().lower(), Organization.kind == OrganizationKind.PARTNER.value)
        ).scalar_one_or_none()
        if pid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Platform '{partner_slug}' not found.")
    pf = (Store.partner_organization_id == pid,) if pid else ()                      # every store query below is limited to the channel
    pids = [Organization.id == pid] if pid else []                                   # and every partner list
    today = _today()
    repo = OrderEntryRepository(db)

    # --- trend: last `days` days, org-wide ---
    start = today - timedelta(days=days - 1)
    totals = repo.daily_totals_between(org_id, start, today, partner_slug=partner_slug.strip().lower() if partner_slug else None)
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
        .where(Store.organization_id == org_id, *pf)
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
        .where(Store.organization_id == org_id)          # every platform: this is a breakdown BY platform, not a mixed total
        .group_by(Organization.id, Organization.slug, Organization.name, Store.status)
        .order_by(Organization.name)
    ).all()
    by_platform: dict[uuid.UUID, dict] = {}
    # Every active partner is listed, even one with no stores yet (e.g. a freshly deployed Zepto).
    for pid, slug, label in db.execute(
        select(Organization.id, Organization.slug, Organization.name)
        .where(Organization.kind == OrganizationKind.PARTNER.value, Organization.is_active.is_(True))
        .order_by(Organization.name)
    ).all():
        by_platform[pid] = {"slug": slug, "label": label, "LIVE": 0, "PENDING": 0, "CLOSE": 0}
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
            .where(Store.organization_id == org_id, *pf)
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
            .where(Store.organization_id == org_id, *pf, Store.status != StoreStatus.LIVE.value)
            .order_by(Store.status, Store.name)
            .limit(50)
        ).all()
    ]

    # --- live stores with no order in the last 30 days ---
    recent = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date >= today - timedelta(days=29))
    dormant_where = (Store.organization_id == org_id, *pf, Store.status == StoreStatus.LIVE.value, ~recent)
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
        select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value, *pids)
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
        .where(Store.organization_id == org_id, *pf)
        .group_by(Region.name)
        .order_by(func.count(Store.id).desc())
    ).all()
    stores_by_region = [
        CoverageRow(label=r[0] or "Unassigned", live=int(r[1] or 0), total=int(r[2]))
        for r in region_rows
    ]

    state_rows = db.execute(
        select(Store.state, live_case, func.count(Store.id))
        .where(Store.organization_id == org_id, *pf)
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


def backmonth_open_until(today: date) -> date | None:
    """The last day on which employees may still mark LAST month's dates (the Nth day of this month), or None when that is switched off."""
    grace = settings.BACKMONTH_GRACE_DAYS
    return today.replace(day=1) + timedelta(days=grace - 1) if grace > 0 else None


def _previous_month(today: date) -> tuple[int, int]:
    last = today.replace(day=1) - timedelta(days=1)
    return last.year, last.month


def employee_can_mark_month(year: int, month: int, today: date) -> bool:
    """This month always; last month too while the grace days at the start of this month last."""
    if (year, month) == (today.year, today.month):
        return True
    until = backmonth_open_until(today)
    return until is not None and today <= until and (year, month) == _previous_month(today)


def _check_order_date(order_date: date, *, allow_any_month: bool = False) -> None:
    today = _today()
    if order_date > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You can't mark a future date.")
    if not allow_any_month and not employee_can_mark_month(order_date.year, order_date.month, today):
        until = backmonth_open_until(today)
        if (order_date.year, order_date.month) == _previous_month(today):
            why = f"Last month's entries could only be added until {until:%d %b}. Ask an admin to add this one." if until else "Last month's entries can no longer be added. Ask an admin to add this one."
        else:
            why = "Orders can only be marked for dates in the current month" + (f" (and last month until {until:%d %b})" if until else "") + "."
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, why)
