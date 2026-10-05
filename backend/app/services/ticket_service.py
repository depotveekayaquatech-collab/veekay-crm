"""
Tickets: who may see / raise / move a ticket, plus the admin insights.

Three kinds of caller:
  admin    (tickets.manage)      every ticket in every region; assigns, sets priority, any status change
  partner  (a Blinkit/Zepto login) tickets for stores of its own platform; can confirm (close) or reopen
  staff    (field employee)      tickets for stores they handle (their region / assigned states) or raised by them;
                                 can start and resolve them
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.store import Store
from app.models.ticket import (
    ACTIVE_STATUSES,
    DELIVERY_CATEGORIES,
    SLA_HOURS,
    Ticket,
    TicketComment,
    TicketStatus,
)
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.common import Page, PageParams
from app.schemas.ticket import (
    Assignee,
    Bucket,
    CategoryCount,
    CommentOut,
    Hotspot,
    StoreBrief,
    TicketAnalytics,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketSummary,
    TicketUpdate,
    TrendPoint,
)
from app.services import activity_service, assignment_service

ADMIN, PARTNER, STAFF = "admin", "partner", "staff"

# actor kind -> {from_status: {allowed to_status}}
_MOVES: dict[str, dict[str, set[str]]] = {
    STAFF: {
        "OPEN": {"IN_PROGRESS", "RESOLVED"},
        "IN_PROGRESS": {"RESOLVED", "OPEN"},
    },
    PARTNER: {
        "RESOLVED": {"CLOSED", "OPEN"},
        "CLOSED": {"OPEN"},
    },
}
_ALL = {s.value for s in TicketStatus}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def actor_kind(db: Session, user: User, perms: set[str]) -> str:
    if "tickets.manage" in perms:
        return ADMIN
    if assignment_service.is_partner_account(db, user):
        return PARTNER
    return STAFF


def _next_statuses(kind: str, current: str) -> list[str]:
    if kind == ADMIN:
        return sorted(_ALL - {current}, key=["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"].index)
    return sorted(_MOVES.get(kind, {}).get(current, set()), key=["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"].index)


def _due(priority: str, start: datetime) -> datetime:
    return start + timedelta(hours=SLA_HOURS.get(priority, 48))


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------

def _scope(db: Session, user: User, kind: str):
    """SQL condition limiting Ticket rows to what this caller may see."""
    org = Ticket.organization_id == user.organization_id
    if kind == ADMIN:
        return org
    if kind == PARTNER:
        if user.platform_organization_id is None:
            return false()
        return and_(org, Ticket.partner_organization_id == user.platform_organization_id)
    ids = assignment_service.visible_store_ids(db, user)
    mine = Ticket.created_by_user_id == user.id
    return and_(org, or_(Ticket.store_id.in_(ids), mine) if ids else mine)


def _can_use_store(db: Session, user: User, kind: str, store: Store) -> bool:
    if store.organization_id != user.organization_id:
        return False
    if kind == ADMIN:
        return True
    if kind == PARTNER:
        return store.partner_organization_id == user.platform_organization_id
    return store.id in assignment_service.visible_store_ids(db, user)


def _load(db: Session, user: User, kind: str, ticket_id: uuid.UUID) -> Ticket:
    t = db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id, _scope(db, user, kind))
        .options(*_eager())
    ).unique().scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found.")
    return t


def _eager():
    return (
        joinedload(Ticket.store).joinedload(Store.region),
        joinedload(Ticket.store).joinedload(Store.partner_organization),
        joinedload(Ticket.created_by),
        joinedload(Ticket.assigned_to),
    )


# --------------------------------------------------------------------------
# mapping
# --------------------------------------------------------------------------

def _brief(s: Store) -> StoreBrief:
    return StoreBrief(
        id=s.id, name=s.name, code=s.external_code, city=s.city, state=s.state,
        region_id=s.region_id, region_name=s.region.name if s.region else None,
        vendor_name=s.vendor_name, vendor_number=s.vendor_number,
        platform_slug=s.partner_organization.slug if s.partner_organization else None,
        platform_name=s.partner_organization.name if s.partner_organization else None,
    )


def _overdue(t: Ticket, now: datetime) -> bool:
    return t.status in ACTIVE_STATUSES and t.due_at is not None and t.due_at < now


def _out(t: Ticket, kind: str, comments: int, now: datetime) -> TicketOut:
    return TicketOut(
        id=t.id, number=t.number, store=_brief(t.store), category=t.category, priority=t.priority, status=t.status,
        title=t.title, description=t.description,
        created_by_name=t.created_by.full_name if t.created_by else (t.reporter or None),
        source=t.source,
        assigned_to_id=t.assigned_to_user_id, assigned_to_name=t.assigned_to.full_name if t.assigned_to else None,
        created_at=t.created_at, updated_at=t.updated_at, due_at=t.due_at, resolved_at=t.resolved_at,
        is_overdue=_overdue(t, now), comments_count=comments,
        next_statuses=_next_statuses(kind, t.status), can_assign=kind == ADMIN, can_set_priority=kind == ADMIN,
    )


def _comment_counts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = db.execute(
        select(TicketComment.ticket_id, func.count(TicketComment.id))
        .where(TicketComment.ticket_id.in_(ids), TicketComment.event.is_(None))
        .group_by(TicketComment.ticket_id)
    ).all()
    return {r[0]: int(r[1]) for r in rows}


# --------------------------------------------------------------------------
# list / detail / create / update / comment
# --------------------------------------------------------------------------

def list_tickets(
    db: Session, user: User, kind: str, params: PageParams, *,
    state_filter: str | None, category: str | None, priority: str | None, partner: str | None,
    region_id: uuid.UUID | None, state: str | None, vendor: str | None, q: str | None,
    overdue: bool, mine: bool,
) -> Page[TicketOut]:
    now = _now()
    stmt = select(Ticket).join(Store, Store.id == Ticket.store_id).where(_scope(db, user, kind))
    if state_filter == "active":
        stmt = stmt.where(Ticket.status.in_(ACTIVE_STATUSES))
    elif state_filter == "done":
        stmt = stmt.where(Ticket.status.not_in(ACTIVE_STATUSES))
    elif state_filter and state_filter.upper() in _ALL:
        stmt = stmt.where(Ticket.status == state_filter.upper())
    if category:
        stmt = stmt.where(Ticket.category == category)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if partner:
        from app.models.organization import Organization

        stmt = stmt.join(Organization, Organization.id == Ticket.partner_organization_id).where(Organization.slug == partner)
    if region_id:
        stmt = stmt.where(Store.region_id == region_id)
    if state:
        stmt = stmt.where(func.lower(Store.state) == state.strip().lower())
    if vendor:
        stmt = stmt.where(func.lower(func.coalesce(Store.vendor_name, "")) == vendor.strip().lower())
    if overdue:
        stmt = stmt.where(Ticket.status.in_(ACTIVE_STATUSES), Ticket.due_at < now)
    if mine:
        stmt = stmt.where(or_(Ticket.assigned_to_user_id == user.id, Ticket.created_by_user_id == user.id))
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        digits = q.strip().lstrip("#").lower().removeprefix("tk-")
        conds = [
            func.lower(Ticket.title).like(like), func.lower(Store.name).like(like),
            func.lower(Store.external_code).like(like), func.lower(func.coalesce(Store.city, "")).like(like),
            func.lower(func.coalesce(Store.vendor_name, "")).like(like),
        ]
        if digits.isdigit():
            conds.append(Ticket.number == int(digits))
        stmt = stmt.where(or_(*conds))

    total = db.execute(select(func.count()).select_from(stmt.with_only_columns(Ticket.id).subquery())).scalar_one()
    # Unresolved first, then the most urgent, then newest.
    prio = case((Ticket.priority == "URGENT", 0), (Ticket.priority == "HIGH", 1), (Ticket.priority == "MEDIUM", 2), else_=3)
    active_first = case((Ticket.status.in_(ACTIVE_STATUSES), 0), else_=1)
    rows = db.execute(
        stmt.options(*_eager()).order_by(active_first, prio, Ticket.created_at.desc()).offset(params.offset).limit(params.limit)
    ).unique().scalars().all()
    counts = _comment_counts(db, [t.id for t in rows])
    return Page(items=[_out(t, kind, counts.get(t.id, 0), now) for t in rows], total=total, page=params.page, page_size=params.page_size)


def _assignees(db: Session, user: User, t: Ticket) -> list[Assignee]:
    users = EmployeeRepository(db).all_for_platform(user.organization_id, t.partner_organization_id)
    region = t.store.region_id
    if region:
        same = [u for u in users if u.region_id == region]
        users = same or users
    return [Assignee(id=u.id, name=u.full_name, code=u.employee_code) for u in users[:100]]


def _detail(db: Session, user: User, kind: str, t: Ticket) -> TicketDetail:
    now = _now()
    base = _out(t, kind, 0, now)
    comments = [
        CommentOut(id=c.id, author_name=c.author.full_name if c.author else None, body=c.body, event=c.event, created_at=c.created_at)
        for c in t.comments
    ]
    return TicketDetail(
        **{**base.model_dump(), "comments_count": sum(1 for c in comments if not c.event)},
        comments=comments,
        assignees=_assignees(db, user, t) if kind == ADMIN else [],
    )


def get_ticket(db: Session, user: User, kind: str, ticket_id: uuid.UUID) -> TicketDetail:
    return _detail(db, user, kind, _load(db, user, kind, ticket_id))


def create_ticket(db: Session, user: User, kind: str, payload: TicketCreate) -> TicketDetail:
    store = db.execute(
        select(Store).where(Store.id == payload.store_id).options(joinedload(Store.region), joinedload(Store.partner_organization))
    ).unique().scalar_one_or_none()
    if store is None or not _can_use_store(db, user, kind, store):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't raise a ticket for this store.")

    now = _now()
    ticket = Ticket(
        organization_id=user.organization_id, store_id=store.id, partner_organization_id=store.partner_organization_id,
        category=payload.category, priority=payload.priority, status=TicketStatus.OPEN.value,
        title=payload.title.strip(), description=(payload.description or "").strip() or None,
        created_by_user_id=user.id, due_at=_due(payload.priority, now),
    )
    if kind == ADMIN and payload.assigned_to_id:
        ticket.assigned_to_user_id = _check_assignee(db, user, payload.assigned_to_id)
    db.add(ticket)
    db.flush()
    activity_service.record(
        db, actor=user, action="ticket.created", entity_type="ticket", entity_id=ticket.id,
        metadata={"number": ticket.number, "store": store.name, "category": ticket.category, "priority": ticket.priority},
    )
    db.commit()
    return get_ticket(db, user, kind, ticket.id)


def _check_assignee(db: Session, actor: User, user_id: uuid.UUID) -> uuid.UUID:
    target = db.get(User, user_id)
    if target is None or target.organization_id != actor.organization_id or not target.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That person can't be assigned.")
    return target.id


def _event(db: Session, ticket: Ticket, user: User, text: str) -> None:
    db.add(TicketComment(ticket_id=ticket.id, author_user_id=user.id, body=text, event=text[:64]))


def update_ticket(db: Session, user: User, kind: str, ticket_id: uuid.UUID, payload: TicketUpdate) -> TicketDetail:
    t = _load(db, user, kind, ticket_id)
    now = _now()

    if payload.status and payload.status != t.status:
        if payload.status not in _next_statuses(kind, t.status):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't move this ticket to that status.")
        _event(db, t, user, f"Status: {t.status.replace('_', ' ').title()} → {payload.status.replace('_', ' ').title()}")
        t.status = payload.status
        if payload.status in (TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value):
            t.resolved_at = t.resolved_at or now
        else:
            t.resolved_at = None
            if payload.status == TicketStatus.OPEN.value:  # reopened: the clock starts again
                t.due_at = _due(t.priority, now)

    if kind == ADMIN:
        if payload.priority and payload.priority != t.priority:
            _event(db, t, user, f"Priority: {t.priority.title()} → {payload.priority.title()}")
            t.priority = payload.priority
            t.due_at = _due(payload.priority, t.created_at)
        if payload.unassign and t.assigned_to_user_id:
            _event(db, t, user, "Unassigned")
            t.assigned_to_user_id = None
        elif payload.assigned_to_id and payload.assigned_to_id != t.assigned_to_user_id:
            t.assigned_to_user_id = _check_assignee(db, user, payload.assigned_to_id)
            who = db.get(User, t.assigned_to_user_id)
            _event(db, t, user, f"Assigned to {who.full_name if who else 'someone'}")
    elif payload.priority or payload.assigned_to_id or payload.unassign:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can change priority or assignment.")

    activity_service.record(
        db, actor=user, action="ticket.updated", entity_type="ticket", entity_id=t.id,
        metadata={"number": t.number, "status": t.status, "priority": t.priority},
    )
    db.commit()
    db.expire_all()
    return get_ticket(db, user, kind, ticket_id)


def add_comment(db: Session, user: User, kind: str, ticket_id: uuid.UUID, body: str) -> TicketDetail:
    t = _load(db, user, kind, ticket_id)
    db.add(TicketComment(ticket_id=t.id, author_user_id=user.id, body=body.strip()))
    t.updated_at = _now()
    db.commit()
    db.expire_all()
    return get_ticket(db, user, kind, ticket_id)


def store_choices(db: Session, user: User, kind: str, q: str | None, limit: int = 30) -> list[StoreBrief]:
    needle = (q or "").strip().lower()
    if kind == STAFF:
        stores = assignment_service.visible_stores(db, user)
    else:
        stmt = (
            select(Store)
            .where(Store.organization_id == user.organization_id)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
            .order_by(Store.name)
        )
        if kind == PARTNER:
            stmt = stmt.where(Store.partner_organization_id == user.platform_organization_id)
        if needle:
            like = f"%{needle}%"
            stmt = stmt.where(or_(
                func.lower(Store.name).like(like), func.lower(Store.external_code).like(like),
                func.lower(func.coalesce(Store.city, "")).like(like),
            ))
        stores = list(db.execute(stmt.limit(limit)).unique().scalars().all())
    if needle and kind == STAFF:
        stores = [s for s in stores if needle in " ".join(filter(None, [s.name, s.external_code, s.city])).lower()]
    return [_brief(s) for s in stores[:limit]]


# --------------------------------------------------------------------------
# admin insights
# --------------------------------------------------------------------------

def _severity(overdue: int, delivery: int) -> str:
    if overdue >= 2 or delivery >= 5:
        return "high"
    if overdue >= 1 or delivery >= 2:
        return "medium"
    return "ok"


def analytics(db: Session, admin: User, days: int = 30) -> TicketAnalytics:
    days = min(max(days, 7), 90)
    now = _now()
    since = now - timedelta(days=days)
    tickets = db.execute(
        select(Ticket)
        .where(Ticket.organization_id == admin.organization_id, or_(Ticket.created_at >= since, Ticket.status.in_(ACTIVE_STATUSES)))
        .options(*_eager())
    ).unique().scalars().all()

    def in_window(t: Ticket) -> bool:
        return t.created_at >= since

    def buckets(key) -> list[Bucket]:
        agg: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "active": 0, "delivery": 0, "overdue": 0})
        for t in tickets:
            a = agg[key(t)]
            if in_window(t):
                a["total"] += 1
                if t.category in DELIVERY_CATEGORIES:
                    a["delivery"] += 1
            if t.status in ACTIVE_STATUSES:
                a["active"] += 1
                if _overdue(t, now):
                    a["overdue"] += 1
        out = [Bucket(label=k, severity=_severity(v["overdue"], v["delivery"]), **v) for k, v in agg.items()]
        return sorted(out, key=lambda b: (b.overdue, b.delivery, b.active, b.total), reverse=True)

    by_store: dict[uuid.UUID, dict] = {}
    for t in tickets:
        s = by_store.setdefault(t.store_id, {"store": t.store, "active": 0, "delivery": 0, "overdue": 0, "total": 0})
        if in_window(t):
            s["total"] += 1
            if t.category in DELIVERY_CATEGORIES:
                s["delivery"] += 1
        if t.status in ACTIVE_STATUSES:
            s["active"] += 1
            if _overdue(t, now):
                s["overdue"] += 1
    hotspots = [
        Hotspot(
            store_id=v["store"].id, name=v["store"].name, code=v["store"].external_code, state=v["store"].state,
            region_name=v["store"].region.name if v["store"].region else None, vendor_name=v["store"].vendor_name,
            platform_name=v["store"].partner_organization.name if v["store"].partner_organization else None,
            active=v["active"], delivery=v["delivery"], overdue=v["overdue"], total=v["total"],
        )
        for v in by_store.values() if v["active"] or v["delivery"]
    ]
    hotspots.sort(key=lambda h: (h.overdue * 3 + h.delivery * 2 + h.active), reverse=True)

    cat: dict[str, int] = defaultdict(int)
    for t in tickets:
        if in_window(t):
            cat[t.category] += 1

    trend: list[TrendPoint] = []
    today = now.date()
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        trend.append(TrendPoint(
            label=f"{d.strftime('%a')} {d.day}",
            created=sum(1 for t in tickets if t.created_at.date() == d),
            resolved=sum(1 for t in tickets if t.resolved_at and t.resolved_at.date() == d),
        ))

    resolved = [t for t in tickets if t.resolved_at and in_window(t)]
    avg = round(sum((t.resolved_at - t.created_at).total_seconds() for t in resolved) / len(resolved) / 3600, 1) if resolved else None
    summary = TicketSummary(
        open=sum(1 for t in tickets if t.status == TicketStatus.OPEN.value),
        in_progress=sum(1 for t in tickets if t.status == TicketStatus.IN_PROGRESS.value),
        overdue=sum(1 for t in tickets if _overdue(t, now)),
        delivery_active=sum(1 for t in tickets if t.status in ACTIVE_STATUSES and t.category in DELIVERY_CATEGORIES),
        raised=sum(1 for t in tickets if in_window(t)),
        resolved=len(resolved),
        avg_resolution_hours=avg,
    )
    return TicketAnalytics(
        days=days, summary=summary,
        by_region=buckets(lambda t: t.store.region.name if t.store.region else "No region"),
        by_state=buckets(lambda t: t.store.state or "No state")[:15],
        by_vendor=buckets(lambda t: (t.store.vendor_name or "").strip() or "No vendor")[:15],
        by_platform=buckets(lambda t: t.store.partner_organization.name if t.store.partner_organization else "—"),
        by_category=[CategoryCount(category=k, count=v) for k, v in sorted(cat.items(), key=lambda kv: -kv[1])],
        trend=trend, hotspots=hotspots[:10],
    )


# --------------------------------------------------------------------------
# tickets pushed in from outside (Google Apps Script)
# --------------------------------------------------------------------------

_CATEGORY_WORDS = (
    ("NO_DELIVERY", ("not deliver", "no delivery", "didn't deliver", "didnt deliver", "missed", "not received", "never came")),
    ("LATE_DELIVERY", ("late", "delay", "delayed")),
    ("SHORT_SUPPLY", ("short", "less", "quantity", "missing bottle", "fewer")),
    ("DAMAGED", ("damage", "leak", "broken", "crack")),
    ("QUALITY", ("quality", "dirty", "taste", "smell", "contaminat", "impure")),
    ("BILLING", ("bill", "invoice", "payment", "charge")),
)
_CATEGORY_VALUES = {"LATE_DELIVERY", "NO_DELIVERY", "SHORT_SUPPLY", "QUALITY", "DAMAGED", "BILLING", "OTHER"}


def normalise_category(text: str | None) -> str:
    """Free text from a form ("Water arrived late") -> one of our categories; anything unrecognised is OTHER."""
    t = (text or "").strip()
    if t.upper().replace(" ", "_") in _CATEGORY_VALUES:
        return t.upper().replace(" ", "_")
    low = t.lower()
    for value, words in _CATEGORY_WORDS:
        if any(w in low for w in words):
            return value
    return "OTHER"


def normalise_priority(text: str | None) -> str:
    low = (text or "").strip().lower()
    for value, words in (("URGENT", ("urgent", "critical", "emergency")), ("HIGH", ("high", "important")), ("LOW", ("low", "minor"))):
        if any(w in low for w in words):
            return value
    return "MEDIUM"


def create_external(
    db: Session, org_id: uuid.UUID, *, external_id: str, store_code: str, platform: str | None, store_name: str | None,
    category: str | None, priority: str | None, title: str, description: str | None, reporter: str | None,
    raised_at: datetime | None,
) -> tuple[Ticket, bool]:
    """Create a ticket from an outside system. Returns (ticket, created). Sending the same external_id again is a no-op."""
    existing = db.execute(
        select(Ticket).where(Ticket.organization_id == org_id, Ticket.external_id == external_id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    stmt = select(Store).where(Store.organization_id == org_id, func.lower(Store.external_code) == store_code.strip().lower())
    if platform:
        from app.models.organization import Organization

        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == platform.strip().lower())
    matches = db.execute(stmt.options(joinedload(Store.partner_organization))).unique().scalars().all()
    if not matches and store_name:
        matches = db.execute(
            select(Store).where(Store.organization_id == org_id, func.lower(Store.name) == store_name.strip().lower())
        ).unique().scalars().all()
    if not matches:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No store with code '{store_code}'" + (f" on {platform}" if platform else "") + ".")
    if len(matches) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Store code '{store_code}' exists on more than one platform — send \"platform\" (blinkit / zepto).",
        )
    store = matches[0]

    now = _now()
    start = raised_at if raised_at and raised_at <= now else now
    prio = normalise_priority(priority)
    ticket = Ticket(
        organization_id=org_id, store_id=store.id, partner_organization_id=store.partner_organization_id,
        category=normalise_category(category), priority=prio, status=TicketStatus.OPEN.value,
        title=title.strip()[:160], description=(description or "").strip() or None,
        created_by_user_id=None, source="google", external_id=external_id[:128], reporter=(reporter or "").strip()[:255] or None,
        due_at=_due(prio, start),
    )
    ticket.created_at = start
    db.add(ticket)
    db.commit()
    return ticket, True
