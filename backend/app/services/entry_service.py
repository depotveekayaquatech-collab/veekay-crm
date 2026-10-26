"""Entries as the supervising levels see them: search (Entry Review / team view), one entry's full timeline, the verification workflow (a Team Lead's verify,
a Reviewer's request-for-check and direct review, corrections by any of them, comments), and the assignment of the Team Lead / Entry Reviewer roles. Who may do what is decided by core.entry_access; the history itself is
written by database triggers (migration 0052), so this module never builds or edits an audit event by hand.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, column, exists, func, or_, select, table, text
from sqlalchemy.orm import Session, aliased

from app.core import audit_context
from app.core.config import settings
from app.core.entry_access import (
    PERM_REVIEW, REVIEWER_ROLE, STATUS_REVIEWED, STATUS_SUBMITTED, STATUS_VERIFIED, TEAM_LEAD_ROLE, EntryScope, Level, owned_clause, scope_for,
)
from app.core.roles import ADMIN, DEVELOPER, PARTNER
from app.models.order_entry import EntrySource, OrderEntry
from app.models.order_entry_event import OrderEntryEvent
from app.models.organization import Organization
from app.models.role import Role
from app.models.store import Store
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services import activity_service, security_event_service, staff_notify
from app.services.entry_changes import STATUS_LABEL

_JOURNAL = table("order_mark_journal", column("store_id"), column("order_date"), column("outcome"), column("organization_id"))

MAX_PAGE = 100
REVIEW_ACTIONS = {"reviewed": "reviewed", "flagged": "flagged", "needs_correction": "needs_correction", "clear": "none"}
VERIFICATION_FILTERS = ("pending_l2", "verified_l2", "reviewed_l3", "requested")
MAX_COMMENT = 1000
MAX_VERIFY_STORE = 3000
MIN_REASON = 5


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.DISPLAY_TIMEZONE)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Kolkata")


def _parse_when(value: str | None, *, end: bool = False) -> datetime | None:
    """A moment from a filter. Without an offset it is Indian time (the operation's local time), converted to UTC for the query.
    A bare date means the start of that day, or the END of it for an upper bound."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{value}' is not a valid date or time.") from exc
    if len(value.strip()) <= 10:                                   # date only
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0) + (timedelta(days=1) if end else timedelta(0))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz())
    return dt.astimezone(timezone.utc)


def _deny(db: Session, user: User, scope: EntryScope | None, what: str, target: object = None, detail: dict | None = None) -> None:
    security_event_service.record(
        user, what, target_type="order_entry", target_id=target, detail=detail, role=(scope.level.value if scope else None),
    )


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------

def _flags(e: OrderEntry, store_avg: float | None) -> list[str]:
    out = []
    if e.version > 1:
        out.append("edited")
    if not e.creator_verified:
        out.append("unverified_creator")
    if e.review_status in ("flagged", "needs_correction"):
        out.append(e.review_status)
    mine = e.bottle_count - e.cash_adjustment
    if mine == 0:
        out.append("zero_count")
    if store_avg and store_avg > 0 and mine >= max(3 * store_avg, 20):
        out.append("unusually_high")
    if e.created_at and e.created_by_user_id and (e.created_at.date() - e.order_date).days > 3:
        out.append("entered_late")
    return out


def _names(db: Session, entries: list[OrderEntry]) -> dict[uuid.UUID, str]:
    """{user id: full name} for everybody named by the verification state of these entries (one query for the whole page)."""
    ids = {i for e in entries for i in (e.verified_by_user_id, e.l3_reviewed_by_user_id, e.check_requested_by_user_id) if i}
    if not ids:
        return {}
    return {r[0]: r[1] for r in db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))}


def _verification(e: OrderEntry, names: dict[uuid.UUID, str]) -> dict:
    return {
        "status": e.verification_status, "label": STATUS_LABEL.get(e.verification_status, e.verification_status),
        "verified_by": None if e.verified_by_user_id is None else {"id": e.verified_by_user_id, "name": names.get(e.verified_by_user_id), "at": e.verified_at},
        "reviewed_by": None if e.l3_reviewed_by_user_id is None else {"id": e.l3_reviewed_by_user_id, "name": names.get(e.l3_reviewed_by_user_id), "at": e.l3_reviewed_at},
        "check_requested": None if e.check_requested_at is None else {
            "by_id": e.check_requested_by_user_id, "by_name": names.get(e.check_requested_by_user_id), "at": e.check_requested_at, "note": e.check_request_note},
    }


def _row(e: OrderEntry, s: Store, platform: Organization | None, modifier_name: str | None, legacy_marker: str | None,
         scope: EntryScope, store_avg: float | None, names: dict[uuid.UUID, str] | None = None) -> dict:
    admin_view = scope.level in (Level.ADMINISTRATOR, Level.REVIEWER)
    names = names or {}
    pid = s.partner_organization_id
    return {
        "entry_id": e.id, "version": e.version,
        "store": {"id": s.id, "name": s.name, "crm_code": s.crm_code, "outlet_id": s.external_code, "status": s.status, "entity": s.entity,
                  "platform": platform.name if platform else None, "platform_slug": platform.slug if platform else None},
        "order_date": e.order_date,
        "employee_count": e.bottle_count - e.cash_adjustment,
        "bottle_count": e.bottle_count if admin_view else None,        # the final figure incl. any developer adjustment: reviewers / admins only
        "cash_adjustment": e.cash_adjustment if admin_view else None,
        "source": e.source,
        "creator": {"id": e.created_by_user_id, "name": e.created_by_name, "code": e.created_by_code, "role": e.created_by_role,
                    "verified": e.creator_verified, "via": e.created_via,
                    "last_recorded_marker": None if e.creator_verified else legacy_marker},
        "created_at": e.created_at, "client_submitted_at": e.client_submitted_at,
        "last_modified": None if e.last_modified_at is None else {
            "by_id": e.last_modified_by_user_id, "by_name": modifier_name, "role": e.last_modified_by_role, "at": e.last_modified_at},
        "review": {"status": e.review_status, "by_id": e.reviewed_by_user_id, "at": e.reviewed_at},
        "source_app": e.source_app,
        "request_id": e.request_id if admin_view else None,
        "flags": _flags(e, store_avg),
        "can_edit": scope.can_edit(e, pid),
        "verification": _verification(e, names),
        # What THIS caller may do with the entry right now, decided by the same rules the server enforces on every action.
        "actions": {
            "edit": scope.can_edit(e, pid), "verify": scope.can_verify_entry(e, pid), "review": scope.can_finalise(e, pid),
            "request_check": scope.can_request_check_of(e, pid) and e.check_requested_at is None,
            "flag": scope.can_review and scope.allows(e, pid), "comment": scope.can_view_history,
        },
    }


def _store_averages(db: Session, scope: EntryScope, store_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
    if not store_ids:
        return {}
    since = date.today() - timedelta(days=45)
    rows = db.execute(
        select(OrderEntry.store_id, func.avg(OrderEntry.bottle_count - OrderEntry.cash_adjustment))
        .where(OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= since, OrderEntry.organization_id == scope.organization_id)
        .group_by(OrderEntry.store_id)
    ).all()
    return {r[0]: float(r[1]) for r in rows}


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def _like(text_: str) -> str:
    return "%" + text_.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(db: Session, user: User, perms: set[str], f: dict, page: int, page_size: int) -> dict:
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_search_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE)
    if f.get("deleted"):
        return _search_cleared(db, scope, f, page, page_size)

    Modifier = aliased(User)
    Marker = aliased(User)
    stmt = (
        select(OrderEntry, Store, Organization, Modifier.full_name, Marker.full_name)
        .join(Store, Store.id == OrderEntry.store_id)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .outerjoin(Modifier, Modifier.id == OrderEntry.last_modified_by_user_id)
        .outerjoin(Marker, Marker.id == OrderEntry.marked_by_user_id)
        .where(*scope.conditions())
    )
    if scope.platform_id is not None:
        stmt = stmt.where(Store.partner_organization_id == scope.platform_id)

    if f.get("entry_id"):
        stmt = stmt.where(OrderEntry.id == f["entry_id"])
    if f.get("store_id"):
        stmt = stmt.where(OrderEntry.store_id == f["store_id"])
    if f.get("store"):
        k = _like(f["store"])
        stmt = stmt.where(or_(Store.name.ilike(k, escape="\\"), Store.crm_code.ilike(k, escape="\\"), Store.external_code.ilike(k, escape="\\")))
    if f.get("outlet_id"):
        stmt = stmt.where(func.lower(Store.external_code) == f["outlet_id"].strip().lower())
    if f.get("platform"):
        stmt = stmt.where(Organization.slug == f["platform"].strip().lower())
    if f.get("creator"):
        k = _like(f["creator"])
        stmt = stmt.where(or_(OrderEntry.created_by_name.ilike(k, escape="\\"), OrderEntry.created_by_code.ilike(k, escape="\\")))
    if f.get("creator_id"):
        stmt = stmt.where(OrderEntry.created_by_user_id == f["creator_id"])
    if f.get("creator_role"):
        stmt = stmt.where(OrderEntry.created_by_role == f["creator_role"].strip().lower())
    if f.get("modifier"):
        k = _like(f["modifier"])
        stmt = stmt.where(or_(Modifier.full_name.ilike(k, escape="\\"), Modifier.employee_code.ilike(k, escape="\\")))
    if f.get("team_lead"):
        k = _like(f["team_lead"])
        leads = select(User.id).where(User.organization_id == scope.organization_id,
                                      or_(User.full_name.ilike(k, escape="\\"), User.employee_code.ilike(k, escape="\\")))
        team = select(User.id).where(User.reports_to_user_id.in_(leads))
        stmt = stmt.where(or_(OrderEntry.created_by_user_id.in_(leads), OrderEntry.created_by_user_id.in_(team),
                              OrderEntry.last_modified_by_user_id.in_(leads)))
    if f.get("date_from"):
        stmt = stmt.where(OrderEntry.order_date >= f["date_from"])
    if f.get("date_to"):
        stmt = stmt.where(OrderEntry.order_date <= f["date_to"])
    t_from, t_to = _parse_when(f.get("created_from")), _parse_when(f.get("created_to"), end=True)
    if t_from:
        stmt = stmt.where(OrderEntry.created_at >= t_from)
    if t_to:
        stmt = stmt.where(OrderEntry.created_at < t_to)
    if f.get("review_status"):
        stmt = stmt.where(OrderEntry.review_status == f["review_status"])
    verification = f.get("verification")
    if verification == "pending_l2":
        stmt = stmt.where(OrderEntry.verification_status == STATUS_SUBMITTED)
    elif verification == "verified_l2":
        stmt = stmt.where(OrderEntry.verification_status == STATUS_VERIFIED)
    elif verification == "reviewed_l3":
        stmt = stmt.where(OrderEntry.verification_status == STATUS_REVIEWED)
    elif verification == "requested":
        stmt = stmt.where(OrderEntry.verification_status == STATUS_SUBMITTED, OrderEntry.check_requested_at.is_not(None))
    if f.get("edited") is True:
        stmt = stmt.where(OrderEntry.version > 1)
    if f.get("edited") is False:
        stmt = stmt.where(OrderEntry.version == 1)
    if f.get("flagged"):
        stmt = stmt.where(OrderEntry.review_status.in_(("flagged", "needs_correction")))
    if f.get("unverified"):
        stmt = stmt.where(OrderEntry.creator_verified.is_(False))
    if f.get("source"):
        k = _like(f["source"])
        stmt = stmt.where(or_(OrderEntry.created_via.ilike(k, escape="\\"), OrderEntry.source_app.ilike(k, escape="\\"), OrderEntry.source.ilike(k, escape="\\")))
    for flag, outcome in (("failed_sync", "rejected"), ("duplicate_attempts", "duplicate")):
        if f.get(flag):
            stmt = stmt.where(exists().where(and_(
                _JOURNAL.c.store_id == OrderEntry.store_id, _JOURNAL.c.order_date == OrderEntry.order_date, _JOURNAL.c.outcome == outcome)))

    total = db.execute(select(func.count()).select_from(stmt.with_only_columns(OrderEntry.id).order_by(None).subquery())).scalar_one()
    order = (OrderEntry.check_requested_at.desc(), OrderEntry.id.desc()) if verification == "requested" else         (OrderEntry.order_date.desc(), OrderEntry.created_at.desc(), OrderEntry.id.desc())
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    avgs = _store_averages(db, scope, [r[1].id for r in rows])
    names = _names(db, [r[0] for r in rows])
    items = [_row(e, s, p, modifier, marker, scope, avgs.get(s.id), names) for e, s, p, modifier, marker in rows]
    return {"total": int(total), "page": page, "page_size": page_size, "level": scope.level.value, "items": items}


def _search_cleared(db: Session, scope: EntryScope, f: dict, page: int, page_size: int) -> dict:
    """Entries that were removed (so they are no longer rows): found through the history, with who removed them and what was there."""
    ev = OrderEntryEvent
    first = aliased(OrderEntryEvent)
    stmt = (
        select(ev, Store)
        .outerjoin(Store, Store.id == ev.store_id)
        .where(ev.event_type == "CLEARED", ev.organization_id == scope.organization_id)
        .where(~exists().where(and_(OrderEntry.id == ev.entry_id)))
    )
    if scope.creator_ids is not None:                     # a Team Lead sees removals of entries their team created
        stmt = stmt.where(exists().where(and_(first.entry_id == ev.entry_id, first.event_type.in_(("CREATED", "BASELINE")),
                                              first.actor_user_id.in_(list(scope.creator_ids)))))
    if scope.platform_id is not None:
        stmt = stmt.where(Store.partner_organization_id == scope.platform_id)
    if f.get("store_id"):
        stmt = stmt.where(ev.store_id == f["store_id"])
    if f.get("entry_id"):
        stmt = stmt.where(ev.entry_id == f["entry_id"])
    if f.get("store"):
        k = _like(f["store"])
        stmt = stmt.where(or_(Store.name.ilike(k, escape="\\"), Store.crm_code.ilike(k, escape="\\"), Store.external_code.ilike(k, escape="\\")))
    t_from, t_to = _parse_when(f.get("created_from")), _parse_when(f.get("created_to"), end=True)
    if t_from:
        stmt = stmt.where(ev.created_at >= t_from)
    if t_to:
        stmt = stmt.where(ev.created_at < t_to)
    total = db.execute(select(func.count()).select_from(stmt.with_only_columns(ev.id).order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.order_by(ev.created_at.desc(), ev.seq.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{
        "entry_id": e.entry_id, "cleared": True,
        "store": None if s is None else {"id": s.id, "name": s.name, "crm_code": s.crm_code, "outlet_id": s.external_code, "status": s.status},
        "order_date": (e.old_values or {}).get("order_date"), "employee_count": (e.old_values or {}).get("bottle_count"),
        "removed_at": e.created_at, "removed_by": {"id": e.actor_user_id, "name": e.actor_name, "code": e.actor_code, "role": e.actor_role},
        "reason": e.reason,
    } for e, s in rows]
    return {"total": int(total), "page": page, "page_size": page_size, "level": scope.level.value, "items": items}


# --------------------------------------------------------------------------
# one entry
# --------------------------------------------------------------------------

def _authorize(db: Session, user: User, scope: EntryScope, entry_id: uuid.UUID, *, lock: bool = False) -> tuple[OrderEntry | None, Store | None]:
    """The entry (or None for one that was removed) if it is inside the user's scope; otherwise a plain 404 — an out-of-scope id and a made-up id look
    the same — and the attempt goes to the security log."""
    stmt = select(OrderEntry).where(OrderEntry.id == entry_id)
    if lock:
        stmt = stmt.with_for_update()
    entry = db.execute(stmt).scalar_one_or_none()
    if entry is not None:
        store = db.get(Store, entry.store_id)
        if scope.allows(entry, store.partner_organization_id if store else None):
            return entry, store
        _deny(db, user, scope, "entry_access_denied", entry_id, {"reason": "outside scope"})
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found.")
    first = db.execute(select(OrderEntryEvent).where(OrderEntryEvent.entry_id == entry_id).order_by(OrderEntryEvent.seq).limit(1)).scalar_one_or_none()
    if first is None or first.organization_id != scope.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found.")
    store = db.get(Store, first.store_id) if first.store_id else None
    in_team = scope.creator_ids is None or first.actor_user_id in scope.creator_ids
    in_platform = scope.platform_id is None or (store is not None and store.partner_organization_id == scope.platform_id)
    if in_team and in_platform:
        return None, store
    _deny(db, user, scope, "entry_access_denied", entry_id, {"reason": "outside scope (removed entry)"})
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found.")


def _event_out(e: OrderEntryEvent) -> dict:
    return {
        "id": e.id, "seq": e.seq, "type": e.event_type, "at": e.created_at,
        "actor": {"id": e.actor_user_id, "name": e.actor_name, "code": e.actor_code, "role": e.actor_role, "known": e.actor_known},
        "old": e.old_values, "new": e.new_values,
        "changed_fields": sorted(set((e.old_values or {}).keys()) | set((e.new_values or {}).keys())) if e.old_values is not None else None,
        "reason": e.reason, "comment": e.comment, "request_id": e.request_id, "source": e.source, "version": e.entry_version,
    }


def timeline(db: Session, user: User, perms: set[str], entry_id: uuid.UUID) -> dict:
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_history_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    entry, store = _authorize(db, user, scope, entry_id)
    events = db.execute(select(OrderEntryEvent).where(OrderEntryEvent.entry_id == entry_id).order_by(OrderEntryEvent.seq)).scalars().all()
    chain_ok = bool(db.execute(text("SELECT entry_verify_chain(:e)"), {"e": entry_id}).scalar())
    admin_view = scope.level in (Level.ADMINISTRATOR, Level.REVIEWER)
    attempts: list[dict] = []
    if admin_view and store is not None:
        day = entry.order_date if entry is not None else (events[0].new_values or events[-1].old_values or {}).get("order_date") if events else None
        if day:
            attempts = [dict(r) for r in db.execute(
                text("""SELECT j.created_at, j.outcome, j.reason, j.bottle_count, j.action, j.request_key, j.client, u.full_name AS user_name, u.employee_code AS user_code
                        FROM order_mark_journal j LEFT JOIN users u ON u.id = j.user_id
                        WHERE j.store_id = :s AND j.order_date = :d AND j.organization_id = :o ORDER BY j.created_at"""),
                {"s": store.id, "d": day, "o": scope.organization_id}).mappings()]
    out = {
        "entry_id": entry_id, "removed": entry is None, "chain_ok": chain_ok, "level": scope.level.value,
        "store": None if store is None else {"id": store.id, "name": store.name, "crm_code": store.crm_code, "outlet_id": store.external_code, "entity": store.entity},
        "events": [_event_out(e) for e in events], "attempts": attempts,
        "display_timezone": settings.DISPLAY_TIMEZONE,
    }
    if entry is not None:
        marker = db.get(User, entry.marked_by_user_id) if entry.marked_by_user_id else None
        modifier = db.get(User, entry.last_modified_by_user_id) if entry.last_modified_by_user_id else None
        avg = _store_averages(db, scope, [store.id]).get(store.id)
        out["entry"] = _row(entry, store, db.get(Organization, store.partner_organization_id), modifier.full_name if modifier else None,
                            marker.full_name if marker else None, scope, avg, _names(db, [entry]))
    return out


# --------------------------------------------------------------------------
# changes
# --------------------------------------------------------------------------

def _invalidate_reads() -> None:
    from app.core.cache import read_cache

    read_cache.invalidate()


def _locked(db: Session, user: User, scope: EntryScope, entry_id: uuid.UUID, removed_message: str) -> tuple[OrderEntry, Store]:
    entry, store = _authorize(db, user, scope, entry_id, lock=True)
    if entry is None or store is None:
        raise HTTPException(status.HTTP_409_CONFLICT, removed_message)
    return entry, store


def edit_entry(db: Session, user: User, perms: set[str], entry_id: uuid.UUID, new_count: int, reason: str, expected_version: int) -> dict:
    """A correction. A Team Lead may correct only an entry still `submitted` (the edit counts as their verification); a Reviewer or administrator may correct
    any entry (the edit is final). The creator never changes; the old and new values, the reason, the editor, their role and the time go into the
    history in the same transaction, and the database moves the verification state from who changed the number."""
    scope = scope_for(db, user, perms)
    if not scope.can_edit_values:
        _deny(db, user, scope, "entry_edit_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change entries.")
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Say why you are correcting this entry (at least {MIN_REASON} characters).")
    if not (settings.MIN_BOTTLE_COUNT <= new_count <= settings.MAX_BOTTLE_COUNT):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Bottle count must be from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}.")
    entry, store = _locked(db, user, scope, entry_id, "This entry was removed. Mark the day again instead.")
    if scope.level is Level.TEAM_LEAD and entry.verification_status != STATUS_SUBMITTED:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This entry is already {STATUS_LABEL[entry.verification_status].lower()}. Only a Reviewer can change it now.")
    if not scope.can_edit(entry, store.partner_organization_id):
        _deny(db, user, scope, "entry_edit_denied", entry_id, {"reason": "creator not verified or not editable by this level"})
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This entry's creator is not verified, so only a Reviewer or an administrator can change it.")
    if entry.version != expected_version:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail={
            "message": "Someone else changed this entry while you were looking at it. Reload it and check the new value.",
            "current_version": entry.version, "current_employee_count": entry.bottle_count - entry.cash_adjustment})
    if new_count == entry.bottle_count - entry.cash_adjustment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That is already the number on this entry.")
    audit_context.bind(db, user, reason=reason)
    entry.bottle_count = new_count + entry.cash_adjustment        # a developer's cash adjustment stays on top, untouched
    entry.source = EntrySource.ADMIN.value                         # a correction: the sheet import and the employee never overwrite it
    entry.marked_by_user_id = user.id
    db.commit()
    _invalidate_reads()
    return timeline(db, user, perms, entry_id)


def verify_entry(db: Session, user: User, perms: set[str], entry_id: uuid.UUID, comment: str | None) -> dict:
    """Level 2: the Team Lead confirms a `submitted` entry of their team as it stands. Nothing about the number changes."""
    scope = scope_for(db, user, perms)
    if not scope.can_verify:
        _deny(db, user, scope, "entry_verify_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Team Lead can verify entries.")
    entry, _store = _locked(db, user, scope, entry_id, "This entry was removed.")
    if entry.verification_status != STATUS_SUBMITTED:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This entry is already {STATUS_LABEL[entry.verification_status].lower()}.")
    comment = (comment or "").strip()[:MAX_COMMENT]
    audit_context.bind(db, user, comment=comment or None, reason=comment or None)
    entry.verification_status = STATUS_VERIFIED
    db.commit()
    return timeline(db, user, perms, entry_id)


def request_check(db: Session, user: User, perms: set[str], entry_id: uuid.UUID, note: str | None) -> dict:
    """Level 3 / 4: ask the Team Lead of the person who entered it to check a `submitted` entry. Creates the request (shown in the Team Lead's list as
    'Verification requested', with an in-app notification); the Reviewer can still review it themselves."""
    scope = scope_for(db, user, perms)
    if not scope.can_request_check:
        _deny(db, user, scope, "entry_request_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't ask for a check.")
    entry, store = _locked(db, user, scope, entry_id, "This entry was removed.")
    if entry.verification_status != STATUS_SUBMITTED:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This entry is already {STATUS_LABEL[entry.verification_status].lower()}; there is nothing for the Team Lead to check.")
    note = (note or "").strip()[:MAX_COMMENT]
    if entry.check_requested_at is not None and not note:
        return {**timeline(db, user, perms, entry_id), "request": {"already_open": True}}
    lead = None
    if entry.created_by_user_id:
        creator = db.get(User, entry.created_by_user_id)
        lead = db.get(User, creator.reports_to_user_id) if creator is not None and creator.reports_to_user_id else None
    audit_context.bind(db, user, comment=note or None, reason=note or None)
    entry.check_requested_at = datetime.now(timezone.utc)
    entry.check_request_note = note or None
    if lead is not None:
        staff_notify.notify_users(
            db, [lead.id], kind="entry_check", title="Verification requested",
            body=f"{user.full_name} asked you to check {store.name} for {entry.order_date.strftime('%d %b %Y')}." + (f' "{note}"' if note else ""),
            ref_id=entry.id, skip=user.id)
    db.commit()
    return {**timeline(db, user, perms, entry_id), "request": {"already_open": False, "team_lead": None if lead is None else {"id": lead.id, "name": lead.full_name}}}


def review_entry(db: Session, user: User, perms: set[str], entry_id: uuid.UUID, action: str, comment: str | None) -> dict:
    """A Reviewer's / administrator's decision. `reviewed` finalises the entry directly (the Team Lead is no longer needed: the shortcut); flagged /
    needs_correction / clear only set the review mark. None of them changes a value, the creator or the history."""
    scope = scope_for(db, user, perms)
    if not scope.can_review:
        _deny(db, user, scope, "entry_review_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't review entries.")
    if action not in REVIEW_ACTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown review action.")
    comment = (comment or "").strip()
    if action in ("flagged", "needs_correction") and len(comment) < MIN_REASON:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Say what is wrong (at least {MIN_REASON} characters).")
    entry, _store = _locked(db, user, scope, entry_id, "This entry was removed.")
    if action == "reviewed":
        if entry.verification_status == STATUS_REVIEWED and not comment:
            return timeline(db, user, perms, entry_id)
        audit_context.bind(db, user, comment=comment or None, reason=comment or None)
        if entry.verification_status != STATUS_REVIEWED:
            entry.verification_status = STATUS_REVIEWED
        if entry.review_status in ("flagged", "needs_correction"):
            entry.review_status = "none"                       # the reviewer has dealt with it
        db.commit()
        return timeline(db, user, perms, entry_id)
    new_status = REVIEW_ACTIONS[action]
    if entry.review_status == new_status and not comment:
        return timeline(db, user, perms, entry_id)
    audit_context.bind(db, user, comment=comment or None, reason=comment or None)
    entry.review_status = new_status
    db.commit()
    return timeline(db, user, perms, entry_id)


def add_comment(db: Session, user: User, perms: set[str], entry_id: uuid.UUID, text_: str) -> dict:
    """A free-text comment on an entry's history (Team Lead inside their team, Reviewer, administrator). It is appended to the same hash-chained history
    as every other event; it changes nothing about the entry."""
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_comment_denied", entry_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    body = (text_ or "").strip()
    if not body:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write a comment first.")
    if len(body) > MAX_COMMENT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"A comment can be at most {MAX_COMMENT} characters.")
    entry, _store = _locked(db, user, scope, entry_id, "This entry was removed.")
    audit_context.bind(db, user)
    db.execute(
        text("SELECT entry_append_event(CAST(:e AS uuid), CAST(:s AS uuid), CAST(:o AS uuid), 'COMMENTED', CAST(NULL AS jsonb), CAST(NULL AS jsonb), :v, CAST(:a AS uuid), NULL, :c)"),
        {"e": str(entry.id), "s": str(entry.store_id), "o": str(entry.organization_id), "v": entry.version, "a": str(user.id), "c": body},
    )
    db.commit()
    return timeline(db, user, perms, entry_id)


# --------------------------------------------------------------------------
# pickers + counters for the Team Lead / Reviewer screens
# --------------------------------------------------------------------------

def filter_options(db: Session, user: User, perms: set[str], kind: str, q: str | None, limit: int = 20, platform_id: uuid.UUID | None = None) -> list[dict]:
    """Typeahead for the Store-wise and Employee-wise filters. Always inside the caller's scope: a Team Lead gets their team and the stores their team
    entered; a Reviewer / administrator gets the organisation (a platform-limited Reviewer only that platform)."""
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_options_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    limit = max(1, min(limit, 300 if kind == "person" else 50))
    term = _like(q) if q and q.strip() else None
    if kind == "platform":
        # The partners (Blinkit, Zepto ...) the caller can look into: a platform-limited Reviewer has exactly one, a Team Lead those of their team.
        stmt = select(Organization).where(Organization.kind == "partner", Organization.is_active.is_(True))
        if scope.platform_id is not None:
            stmt = stmt.where(Organization.id == scope.platform_id)
        elif scope.creator_ids is not None:
            stmt = stmt.where(Organization.id.in_(select(User.platform_organization_id).where(User.id.in_(list(scope.creator_ids)), User.platform_organization_id.is_not(None))))
        return [{"id": o.id, "name": o.name, "slug": o.slug} for o in db.execute(stmt.order_by(Organization.name)).scalars()]
    if kind == "store":
        stmt = select(Store, Organization).join(Organization, Organization.id == Store.partner_organization_id).where(Store.organization_id == scope.organization_id)
        if scope.platform_id is not None:
            stmt = stmt.where(Store.partner_organization_id == scope.platform_id)
        if scope.creator_ids is not None:
            since = date.today() - timedelta(days=120)
            stmt = stmt.where(Store.id.in_(select(OrderEntry.store_id).where(*scope.conditions(), OrderEntry.order_date >= since)))
        if term:
            stmt = stmt.where(or_(Store.name.ilike(term, escape="\\"), Store.crm_code.ilike(term, escape="\\"), Store.external_code.ilike(term, escape="\\")))
        rows = db.execute(stmt.order_by(Store.name).limit(limit)).all()
        return [{"id": s.id, "name": s.name, "code": s.external_code, "crm_code": s.crm_code, "platform": p.name, "status": s.status} for s, p in rows]
    if kind == "person":
        stmt = select(User).where(User.organization_id == scope.organization_id, User.is_active.is_(True))
        if DEVELOPER not in UserRepository(db).get_role_codes(user.id):          # the developer account is not listed for anyone else
            stmt = stmt.where(User.id.not_in(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == DEVELOPER)))
        if scope.creator_ids is not None:
            stmt = stmt.where(User.id.in_(list(scope.creator_ids)))
        elif scope.platform_id is not None:
            stmt = stmt.where(User.platform_organization_id == scope.platform_id)
        if platform_id is not None:                       # "employees under this partner" (can only narrow the scope, never widen it)
            stmt = stmt.where(User.platform_organization_id == platform_id)
        if term:
            stmt = stmt.where(or_(User.full_name.ilike(term, escape="\\"), User.employee_code.ilike(term, escape="\\")))
        users = db.execute(stmt.order_by(User.full_name).limit(limit)).scalars().all()
        return [{"id": u.id, "name": u.full_name, "code": u.employee_code, "is_me": u.id == user.id} for u in users]
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "kind must be 'platform', 'store' or 'person'.")


def employee_stores(db: Session, user: User, perms: set[str], creator_id: uuid.UUID | None, f: dict) -> dict:
    """One row per store with what state its entries are in: the screen before "open a store". With an employee chosen, only that employee's entries count;
    without one it is every store in the caller's scope (a Team Lead: their team's). Always inside the caller's scope, optionally narrowed by store text / partner / days."""
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_stores_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    employee = db.get(User, creator_id) if creator_id else None
    if creator_id and (employee is None or employee.organization_id != scope.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    v = OrderEntry.verification_status
    stmt = (
        select(
            Store, Organization, func.count(OrderEntry.id), func.count().filter(v == STATUS_SUBMITTED), func.count().filter(v == STATUS_VERIFIED),
            func.count().filter(v == STATUS_REVIEWED), func.count().filter(OrderEntry.check_requested_at.is_not(None)),
            func.sum(OrderEntry.bottle_count - OrderEntry.cash_adjustment), func.max(OrderEntry.order_date),
        )
        .select_from(OrderEntry).join(Store, Store.id == OrderEntry.store_id).join(Organization, Organization.id == Store.partner_organization_id)
        .where(*scope.conditions())
        .group_by(Store.id, Organization.id)
    )
    if creator_id:
        stmt = stmt.where(owned_clause({creator_id}))
    if scope.platform_id is not None:
        stmt = stmt.where(Store.partner_organization_id == scope.platform_id)
    if f.get("platform"):
        stmt = stmt.where(Organization.slug == f["platform"].strip().lower())
    if f.get("store"):
        k = _like(f["store"])
        stmt = stmt.where(or_(Store.name.ilike(k, escape="\\"), Store.crm_code.ilike(k, escape="\\"), Store.external_code.ilike(k, escape="\\")))
    if f.get("date_from"):
        stmt = stmt.where(OrderEntry.order_date >= f["date_from"])
    if f.get("date_to"):
        stmt = stmt.where(OrderEntry.order_date <= f["date_to"])
    wanted = {"pending_l2": v == STATUS_SUBMITTED, "verified_l2": v == STATUS_VERIFIED, "reviewed_l3": v == STATUS_REVIEWED,
              "requested": and_(v == STATUS_SUBMITTED, OrderEntry.check_requested_at.is_not(None))}.get(f.get("verification") or "")
    if wanted is not None:                                # only stores that have at least one entry in that state
        stmt = stmt.having(func.count().filter(wanted) > 0)
    rows = db.execute(stmt.order_by(func.count().filter(v == STATUS_SUBMITTED).desc(), Store.name).limit(1000)).all()
    return {
        "employee": None if employee is None else {"id": employee.id, "name": employee.full_name, "code": employee.employee_code},
        "level": scope.level.value, "verify_to": _verify_target(scope)[0] if (scope.can_review or scope.can_verify) else None,
        "total": len(rows),
        "items": [{
            "store": {"id": s.id, "name": s.name, "crm_code": s.crm_code, "outlet_id": s.external_code, "status": s.status, "entity": s.entity, "platform": p.name},
            "entries": int(n), "pending_l2": int(pend), "verified_l2": int(ver), "reviewed_l3": int(rev), "requested": int(req),
            "bottles": int(bottles or 0), "last_entry": last,
        } for s, p, n, pend, ver, rev, req, bottles, last in rows],
    }


def _store_entries(scope: EntryScope, store_id: uuid.UUID, f: dict) -> list:
    """The entries of one store the caller may see, narrowed to one employee and/or a range of days when asked."""
    conds = [*scope.conditions(), OrderEntry.store_id == store_id]
    if f.get("creator_id"):
        conds.append(owned_clause({f["creator_id"]}))
    if f.get("date_from"):
        conds.append(OrderEntry.order_date >= f["date_from"])
    if f.get("date_to"):
        conds.append(OrderEntry.order_date <= f["date_to"])
    return conds


def _store_in_scope(db: Session, user: User, scope: EntryScope, store_id: uuid.UUID) -> Store:
    """The store, only when the caller has at least one entry of it in scope (so this never hands out any other store's details)."""
    store = db.get(Store, store_id)
    allowed = store is not None and store.organization_id == scope.organization_id and (scope.platform_id is None or store.partner_organization_id == scope.platform_id)
    if allowed and db.execute(select(exists().where(and_(*scope.conditions(), OrderEntry.store_id == store_id)))).scalar():
        return store
    _deny(db, user, scope, "entry_store_denied", store_id)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")


def _is_flagged():
    return OrderEntry.review_status.in_(("flagged", "needs_correction"))


def _verify_target(scope: EntryScope) -> tuple[str, tuple[str, ...]]:
    """What "verify this store" does for this level, and which entries it touches: a Team Lead verifies the `submitted` ones; a Reviewer / administrator
    reviews every one that is not yet reviewed. Entries carrying a flag stay as they are: somebody asked for a correction there."""
    if scope.can_review:
        return STATUS_REVIEWED, (STATUS_SUBMITTED, STATUS_VERIFIED)
    return STATUS_VERIFIED, (STATUS_SUBMITTED,)


def store_review(db: Session, user: User, perms: set[str], store_id: uuid.UUID, f: dict) -> dict:
    """One store opened for checking: its details and contacts, one month of its entries as a calendar, and how many entries are in each state
    (for the chosen employee / days when those are set). Always inside the caller's scope."""
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        _deny(db, user, scope, "entry_store_denied", store_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    store = _store_in_scope(db, user, scope, store_id)
    platform = db.get(Organization, store.partner_organization_id)
    today = datetime.now(_tz()).date()
    year, month = f.get("year") or today.year, f.get("month") or today.month
    first = date(year, month, 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)

    in_month = {**f, "date_from": max(first, f["date_from"]) if f.get("date_from") else first, "date_to": min(last, f["date_to"]) if f.get("date_to") else last}
    rows = db.execute(select(OrderEntry).where(*_store_entries(scope, store_id, in_month))).scalars().all()
    by_day = {e.order_date: e for e in rows}
    days = []
    for n in range(1, last.day + 1):
        d = date(year, month, n)
        e = by_day.get(d)
        days.append({
            "date": d, "day": n, "is_future": d > today, "is_today": d == today,
            "entry": None if e is None else {
                "entry_id": e.id, "count": e.bottle_count - e.cash_adjustment, "status": e.verification_status, "requested": e.check_requested_at is not None,
                "flagged": e.review_status in ("flagged", "needs_correction"), "edited": e.version > 1, "created_by": e.created_by_name,
            },
        })

    v = OrderEntry.verification_status
    target, from_states = _verify_target(scope)
    counts = db.execute(
        select(
            func.count(), func.count().filter(v == STATUS_SUBMITTED), func.count().filter(v == STATUS_VERIFIED), func.count().filter(v == STATUS_REVIEWED),
            func.count().filter(and_(v == STATUS_SUBMITTED, OrderEntry.check_requested_at.is_not(None))), func.count().filter(_is_flagged()),
            func.count().filter(and_(v.in_(from_states), ~_is_flagged())),
        ).select_from(OrderEntry).where(*_store_entries(scope, store_id, f))
    ).one()
    total, pend, ver, rev, req, flagged, todo = (int(x) for x in counts)
    return {
        "store": {
            "id": store.id, "name": store.name, "outlet_id": store.external_code, "crm_code": store.crm_code, "entity": store.entity, "status": store.status,
            "city": store.city, "state": store.state, "region_name": store.region.name if store.region else None,
            "platform": platform.name if platform else None, "platform_slug": platform.slug if platform else None,
            "poc_name": store.poc_name, "poc_number": store.poc_number, "vendor_name": store.vendor_name, "vendor_number": store.vendor_number,
        },
        "year": year, "month": month, "days": days, "level": scope.level.value,
        "counts": {"entries": total, "pending_l2": pend, "verified_l2": ver, "reviewed_l3": rev, "requested": req, "flagged": flagged},
        # what one click on "Verify store" would change, and what it would turn those entries into
        "verify": {"allowed": scope.can_review or scope.can_verify, "to": target, "will_change": todo, "skipped_flagged": flagged},
    }


def verify_store(db: Session, user: User, perms: set[str], store_id: uuid.UUID, f: dict, comment: str | None) -> dict:
    """Verify a whole store in one step instead of entry by entry: "I checked this store" means every entry in view is checked. Same rules as the single
    entry actions (a Team Lead only for their team's `submitted` entries; a Reviewer / administrator for anything not yet reviewed), same history rows, one
    per entry. Flagged entries are left for someone to look at on their own."""
    scope = scope_for(db, user, perms)
    if not (scope.can_review or scope.can_verify):
        _deny(db, user, scope, "entry_verify_denied", store_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't verify entries.")
    store = _store_in_scope(db, user, scope, store_id)
    target, from_states = _verify_target(scope)
    comment = (comment or "").strip()[:MAX_COMMENT]
    entries = db.execute(
        select(OrderEntry).where(*_store_entries(scope, store_id, f), OrderEntry.verification_status.in_(from_states), ~_is_flagged())
        .order_by(OrderEntry.order_date).with_for_update().limit(MAX_VERIFY_STORE + 1)
    ).scalars().all()
    if len(entries) > MAX_VERIFY_STORE:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"That is more than {MAX_VERIFY_STORE} entries. Pick a shorter range of days (Day from / Day to) and verify in parts.")
    audit_context.bind(db, user, comment=comment or None, reason=comment or f"Verified the whole store ({store.name})")
    for e in entries:
        e.verification_status = target
    db.commit()
    _invalidate_reads()
    flagged_left = db.execute(select(func.count()).select_from(OrderEntry).where(*_store_entries(scope, store_id, f), _is_flagged())).scalar_one()
    return {"changed": len(entries), "to": target, "skipped_flagged": int(flagged_left)}


def team_overview(db: Session, user: User, perms: set[str]) -> dict:
    """The Team Lead's dashboard: this month and today for the whole team (people, stores covered, bottles, entries in each state) and one row per person.
    Numbers are the employees' own counts (a developer's cash adjustment is never part of them)."""
    scope = scope_for(db, user, perms)
    if scope.level is not Level.TEAM_LEAD or scope.creator_ids is None:
        _deny(db, user, scope, "team_overview_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This overview is for Team Leads.")
    today = datetime.now(_tz()).date()
    month_start = today.replace(day=1)
    who = func.coalesce(OrderEntry.created_by_user_id, OrderEntry.marked_by_user_id)
    amount = OrderEntry.bottle_count - OrderEntry.cash_adjustment
    v = OrderEntry.verification_status
    base = [*scope.conditions(), OrderEntry.order_date >= month_start, OrderEntry.order_date <= today]
    rows = db.execute(
        select(
            who, func.count(), func.count(func.distinct(OrderEntry.store_id)), func.coalesce(func.sum(amount), 0),
            func.count().filter(v == STATUS_SUBMITTED), func.count().filter(v == STATUS_VERIFIED), func.count().filter(v == STATUS_REVIEWED),
            func.count().filter(OrderEntry.check_requested_at.is_not(None)), func.max(OrderEntry.order_date),
            func.count().filter(OrderEntry.order_date == today), func.coalesce(func.sum(amount).filter(OrderEntry.order_date == today), 0),
        ).where(*base).group_by(who)
    ).all()
    stores = int(db.execute(select(func.count(func.distinct(OrderEntry.store_id))).where(*base)).scalar_one())
    members = {u.id: u for u in db.execute(select(User).where(User.id.in_(list(scope.creator_ids)), User.is_active.is_(True))).scalars()}
    per = {r[0]: r for r in rows}
    people = []
    for uid, u in members.items():
        r = per.get(uid)
        people.append({
            "id": uid, "name": u.full_name, "code": u.employee_code, "is_me": uid == user.id,
            "entries": int(r[1]) if r else 0, "stores": int(r[2]) if r else 0, "bottles": int(r[3]) if r else 0,
            "pending_l2": int(r[4]) if r else 0, "verified_l2": int(r[5]) if r else 0, "reviewed_l3": int(r[6]) if r else 0,
            "requested": int(r[7]) if r else 0, "last_entry": r[8] if r else None, "today_entries": int(r[9]) if r else 0, "today_bottles": int(r[10]) if r else 0,
        })
    people.sort(key=lambda p: (-p["pending_l2"], p["name"]))
    total = lambda k: sum(p[k] for p in people)
    return {
        "month_start": month_start, "today": today,
        "members": len(members), "stores": stores,
        "entries": total("entries"), "bottles": total("bottles"), "today_entries": total("today_entries"), "today_bottles": total("today_bottles"),
        "pending_l2": total("pending_l2"), "verified_l2": total("verified_l2"), "reviewed_l3": total("reviewed_l3"), "requested": total("requested"),
        "not_entered_today": sum(1 for p in people if p["today_entries"] == 0 and not p["is_me"]),
        "people": people,
    }


def summary(db: Session, user: User, perms: set[str], days: int = 30) -> dict:
    """How many entries sit in each state for the caller's scope over the last `days` days (indexed: organisation, state, day)."""
    scope = scope_for(db, user, perms)
    if not scope.can_view_history:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    days = max(1, min(days, 366))
    since = date.today() - timedelta(days=days)
    stmt = (
        select(OrderEntry.verification_status, func.count(), func.count().filter(OrderEntry.check_requested_at.is_not(None)))
        .join(Store, Store.id == OrderEntry.store_id)
        .where(*scope.conditions(), OrderEntry.order_date >= since)
        .group_by(OrderEntry.verification_status)
    )
    if scope.platform_id is not None:
        stmt = stmt.where(Store.partner_organization_id == scope.platform_id)
    counts = {status_: (n, req) for status_, n, req in db.execute(stmt).all()}
    return {
        "since": since, "days": days,
        "pending_l2": counts.get(STATUS_SUBMITTED, (0, 0))[0], "verified_l2": counts.get(STATUS_VERIFIED, (0, 0))[0],
        "reviewed_l3": counts.get(STATUS_REVIEWED, (0, 0))[0], "requested": counts.get(STATUS_SUBMITTED, (0, 0))[1],
    }


# --------------------------------------------------------------------------
# attempts + security log (reviewers / administrators)
# --------------------------------------------------------------------------

def attempts(db: Session, user: User, perms: set[str], *, store_id: uuid.UUID | None, user_id: uuid.UUID | None, outcome: str | None, store: str | None = None,
             date_from: date | None, date_to: date | None, page: int, page_size: int) -> dict:
    scope = scope_for(db, user, perms)
    if not scope.can_store_audit:
        _deny(db, user, scope, "attempts_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE)
    where = ["j.organization_id = :org"]
    params: dict = {"org": scope.organization_id, "lim": page_size, "off": (page - 1) * page_size}
    for cond, key, val in (("j.store_id = :store", "store", store_id), ("j.user_id = :uid", "uid", user_id), ("j.outcome = :outcome", "outcome", outcome),
                           ("j.order_date >= :df", "df", date_from), ("j.order_date <= :dt", "dt", date_to),
                           ("s.partner_organization_id = :plat", "plat", scope.platform_id),
                           ("(s.name ILIKE :sname OR s.external_code ILIKE :sname OR s.crm_code ILIKE :sname)", "sname", _like(store) if store else None)):
        if val is not None:
            where.append(cond)
            params[key] = val
    w = " AND ".join(where)
    base = f"FROM order_mark_journal j LEFT JOIN stores s ON s.id = j.store_id LEFT JOIN users u ON u.id = j.user_id WHERE {w}"
    total = db.execute(text(f"SELECT count(*) {base}"), params).scalar_one()
    rows = db.execute(text(
        f"SELECT j.id, j.created_at, j.order_date, j.bottle_count, j.outcome, j.reason, j.action, j.request_key, j.client, s.id AS store_id, s.name AS store_name, "
        f"s.crm_code, s.external_code AS outlet_id, u.id AS user_id, u.full_name AS user_name, u.employee_code AS user_code {base} "
        f"ORDER BY j.created_at DESC, j.id LIMIT :lim OFFSET :off"), params).mappings().all()
    return {"total": int(total), "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


def security_events(db: Session, user: User, perms: set[str], *, event_type: str | None, page: int, page_size: int) -> dict:
    scope = scope_for(db, user, perms)
    if not scope.can_store_audit:
        _deny(db, user, scope, "security_log_denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE)
    params: dict = {"org": scope.organization_id, "lim": page_size, "off": (page - 1) * page_size}
    w = "organization_id = :org"
    if event_type:
        w += " AND event_type = :et"
        params["et"] = event_type
    total = db.execute(text(f"SELECT count(*) FROM security_events WHERE {w}"), params).scalar_one()
    rows = db.execute(text(f"SELECT * FROM security_events WHERE {w} ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params).mappings().all()
    return {"total": int(total), "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


# --------------------------------------------------------------------------
# roles
# --------------------------------------------------------------------------

LEVELS = {"entry_contributor": None, "team_lead": TEAM_LEAD_ROLE, "entry_reviewer": REVIEWER_ROLE}


def set_entry_role(db: Session, actor: User, target_id: uuid.UUID, *, level: str | None, reports_to_id: uuid.UUID | None, set_reports_to: bool) -> dict:
    """Make someone a Team Lead / Entry Reviewer (or back to a plain contributor) and/or say which Team Lead they report to. Administrators only; nobody
    can change their own level; every change is written to the security log. It applies from the person's very next request (permissions and scope are
    read from the database each time; the sign-in token carries identity only)."""
    repo = UserRepository(db)
    actor_roles = set(repo.get_role_codes(actor.id))
    if not (actor_roles & {ADMIN, DEVELOPER}):
        security_event_service.record(actor, "role_change_denied", target_type="user", target_id=target_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can assign these roles.")
    if target_id == actor.id:
        security_event_service.record(actor, "role_change_denied", target_type="user", target_id=target_id, detail={"reason": "self"})
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't change your own role or reporting line.")
    target = db.get(User, target_id)
    if target is None or target.organization_id != actor.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    t_roles = set(repo.get_role_codes(target.id))
    if t_roles & {ADMIN, DEVELOPER, PARTNER}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "These roles are for staff accounts, not admins, developers or partner logins.")

    before = {"roles": sorted(t_roles & {TEAM_LEAD_ROLE, REVIEWER_ROLE}), "reports_to": str(target.reports_to_user_id) if target.reports_to_user_id else None}
    if level is not None:
        if level not in LEVELS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown level.")
        wanted = LEVELS[level]
        for code in (TEAM_LEAD_ROLE, REVIEWER_ROLE):
            role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
            if role is None:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Run the latest database migration.")
            has = db.execute(select(UserRole).where(UserRole.user_id == target.id, UserRole.role_id == role.id)).scalar_one_or_none()
            if code == wanted and has is None:
                db.add(UserRole(user_id=target.id, role_id=role.id))
            elif code != wanted and has is not None:
                db.delete(has)
        if wanted != TEAM_LEAD_ROLE:                       # someone who is no longer a Team Lead leads nobody
            db.execute(User.__table__.update().where(User.reports_to_user_id == target.id).values(reports_to_user_id=None))
    if set_reports_to:
        if reports_to_id is not None:
            lead = db.get(User, reports_to_id)
            if lead is None or lead.organization_id != actor.organization_id or lead.id == target.id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose another Team Lead.")
            if TEAM_LEAD_ROLE not in set(repo.get_role_codes(lead.id)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That person is not a Team Lead.")
        target.reports_to_user_id = reports_to_id
    db.flush()
    after_roles = set(repo.get_role_codes(target.id))
    after = {"roles": sorted(after_roles & {TEAM_LEAD_ROLE, REVIEWER_ROLE}), "reports_to": str(target.reports_to_user_id) if target.reports_to_user_id else None}
    activity_service.record(db, actor=actor, action="employee.entry_role_set", entity_type="employee", entity_id=target.id,
                            metadata={"employee_code": target.employee_code, "before": before, "after": after})
    db.commit()
    security_event_service.record(actor, "role_change", target_type="user", target_id=target.id,
                                  detail={"employee_code": target.employee_code, "before": before, "after": after})
    return {"id": target.id, "level": _level_name(after_roles), "reports_to_id": target.reports_to_user_id}


def _level_name(roles: set[str]) -> str:
    return "entry_reviewer" if REVIEWER_ROLE in roles else "team_lead" if TEAM_LEAD_ROLE in roles else "entry_contributor"


def team_leads(db: Session, user: User) -> list[dict]:
    """Every active Team Lead, for the 'reports to' choice. Administrators only."""
    if not (set(UserRepository(db).get_role_codes(user.id)) & {ADMIN, DEVELOPER}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can see this.")
    rows = db.execute(
        select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(Role.code == TEAM_LEAD_ROLE, User.organization_id == user.organization_id, User.is_active.is_(True)).order_by(User.full_name)
    ).scalars().all()
    return [{"id": u.id, "name": u.full_name, "code": u.employee_code} for u in rows]


def team_members(db: Session, user: User, perms: set[str]) -> list[dict]:
    """The people in the caller's team (a Team Lead: those who report to them); administrators and reviewers get nobody here — they use Store Audit."""
    scope = scope_for(db, user, perms)
    if scope.creator_ids is None:
        return []
    rows = db.execute(select(User).where(User.id.in_(list(scope.creator_ids)), User.is_active.is_(True)).order_by(User.full_name)).scalars().all()
    return [{"id": u.id, "name": u.full_name, "code": u.employee_code, "is_me": u.id == user.id} for u in rows]


# --------------------------------------------------------------------------
# who reports to whom
# --------------------------------------------------------------------------

MAX_ASSIGN = 500


def _require_admin(db: Session, user: User) -> None:
    if not (set(UserRepository(db).get_role_codes(user.id)) & {ADMIN, DEVELOPER}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can see this.")


def hierarchy(db: Session, user: User) -> dict:
    """The chain per platform, top to bottom: administrators, the Reviewers, the Team Leads, and the employees under each Team Lead. Employees with no Team Lead
    (their entries wait for nobody) and employees under a Team Lead of another platform are listed apart, so nobody is left unassigned unnoticed."""
    _require_admin(db, user)
    org = user.organization_id
    roles_of: dict[uuid.UUID, set[str]] = {}
    for uid, code in db.execute(select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).join(User, User.id == UserRole.user_id).where(User.organization_id == org)):
        roles_of.setdefault(uid, set()).add(code)
    people = list(db.execute(select(User).where(User.organization_id == org, User.is_active.is_(True)).order_by(User.full_name)).scalars())
    brief = lambda u: {"id": u.id, "name": u.full_name, "code": u.employee_code}   # noqa: E731
    admins = [brief(u) for u in people if ADMIN in roles_of.get(u.id, set()) and DEVELOPER not in roles_of.get(u.id, set())]
    staff = [u for u in people if roles_of.get(u.id, set()) & {"employee", TEAM_LEAD_ROLE, REVIEWER_ROLE} and not roles_of.get(u.id, set()) & {ADMIN, DEVELOPER, PARTNER}]
    leads_by_id = {u.id: u for u in staff if TEAM_LEAD_ROLE in roles_of[u.id]}

    platforms = []
    for p in db.execute(select(Organization).where(Organization.kind == "partner", Organization.is_active.is_(True)).order_by(Organization.name)).scalars():
        here = [u for u in staff if u.platform_organization_id == p.id]
        team_leads = {u.id: {**brief(u), "employees": []} for u in here if TEAM_LEAD_ROLE in roles_of[u.id]}
        unassigned, elsewhere = [], []
        for u in here:
            r = roles_of[u.id]
            if TEAM_LEAD_ROLE in r or REVIEWER_ROLE in r:
                continue
            lead = leads_by_id.get(u.reports_to_user_id) if u.reports_to_user_id else None
            if lead is None:
                unassigned.append(brief(u))
            elif lead.id in team_leads:
                team_leads[lead.id]["employees"].append(brief(u))
            else:
                elsewhere.append({**brief(u), "team_lead": brief(lead)})
        platforms.append({
            "id": p.id, "name": p.name, "slug": p.slug,
            "reviewers": [brief(u) for u in here if REVIEWER_ROLE in roles_of[u.id]],
            "team_leads": list(team_leads.values()), "unassigned": unassigned, "under_other_platform_lead": elsewhere,
            "employees": sum(len(t["employees"]) for t in team_leads.values()) + len(unassigned) + len(elsewhere),
        })
    return {
        "admins": admins, "reviewers_all_platforms": [brief(u) for u in staff if REVIEWER_ROLE in roles_of[u.id] and u.platform_organization_id is None],
        "platforms": platforms,
    }


def assign_team(db: Session, actor: User, team_lead_id: uuid.UUID, employee_ids: list[uuid.UUID]) -> dict:
    """Put many employees under one Team Lead in one step (each change is checked and logged exactly like the single assignment)."""
    _require_admin(db, actor)
    if not employee_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one employee.")
    if len(employee_ids) > MAX_ASSIGN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Assign at most {MAX_ASSIGN} people at a time.")
    lead = db.get(User, team_lead_id)
    if lead is None or lead.organization_id != actor.organization_id or TEAM_LEAD_ROLE not in set(UserRepository(db).get_role_codes(lead.id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a Team Lead.")
    for emp_id in dict.fromkeys(employee_ids):
        emp = db.get(User, emp_id)
        if emp is not None and emp.platform_organization_id != lead.platform_organization_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{emp.full_name} works on another platform than {lead.full_name}.")
        set_entry_role(db, actor, emp_id, level=None, reports_to_id=lead.id, set_reports_to=True)
    return {"assigned": len(set(employee_ids)), "team_lead": {"id": lead.id, "name": lead.full_name}}
