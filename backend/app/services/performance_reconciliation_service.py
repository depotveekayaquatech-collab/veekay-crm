"""Reproducible, auditable performance reports: snapshots of what was reported, a rebuild of any past moment, and an exact explanation of every difference
between two reports.

WHY THIS EXISTS. The performance report (performance_service) is recounted from the data on every look, and its figure is "store-days of my stores that have an
entry today, out of stores x judged days". Between two looks it can change because entries were added late, an entry was cleared or moved, a new day finished, or
a store changed hands. Nothing recorded what a past report said, so a change could not be told from a loss.

WHAT DOES NOT MOVE IT. Holidays (attendance's business) and WHO entered an entry (the employee, a colleague, a spreadsheet upload by the Developer User): neither
decides whether an entry counts. The creator and the import source stay on every entry and are shown here (`covered_by`, `covered_via`) for audit only.

WHAT IS PROVEN AND WHAT IS INFERRED. The past is rebuilt from records that cannot be edited: `order_entries.created_at` (set once, the database refuses to change
it), `deleted_rows` (a copy of every deleted entry, with the instant, kept by a trigger since migration 0043) and `order_entry_events` (who cleared or moved it,
and why). Entry existence at an instant is therefore PROVEN from the records. Who is in an employee's scope is NOT historised by the application (assignments
and exclusions are overwritten in place), so a past scope is only known for a stored snapshot (its store list is kept) and is otherwise ASSUMED to be today's
(`scope_basis: "current"`). The report says which.

THE ARITHMETIC. For one employee, with S their stores and D the judged days, done = sum over d in D of |S & covered(d)|. From report A to report B the change is
split, exactly and without remainder, into: days that started (the next day finished), stores gained or lost, entries added to days judged in both, and entries
that disappeared from days judged in both. Whatever the records cannot account for (a disappeared entry with no clearing event naming who, or a stored figure
that the records do not reproduce) is `unexplained`, and anything unexplained puts the employee (and the report) in `requires_review`. A decrease is never
called misconduct here: it is a data difference until the records say why.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.entry_access import Level, scope_for
from app.models.deleted_row import DeletedRow
from app.models.order_entry_event import OrderEntryEvent
from app.models.organization import Organization
from app.models.performance_snapshot import PerformanceSnapshot
from app.models.store import Store
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.services import assignment_service, performance_service as ps

VERIFIED, RECONCILED, REVIEW, UNVERIFIABLE = "verified", "reconciled", "requires_review", "unverifiable"
STATUS_LABEL = {
    VERIFIED: "Verified", RECONCILED: "Reconciled with legitimate changes", REVIEW: "Requires review",
    UNVERIFIABLE: "Unable to verify: missing historical evidence",
}
_SEVERITY = {VERIFIED: 0, RECONCILED: 1, UNVERIFIABLE: 2, REVIEW: 3}
SOURCES = ("manual", "scheduled", "report")

# deleted_rows exists from migration 0043 (2026-10-19, IST): an entry deleted before then left no copy, so a past moment before it cannot be rebuilt.
EVIDENCE_START = datetime(2026, 10, 19, tzinfo=ZoneInfo("Asia/Kolkata"))
MAX_RECORDS = 200          # affected records returned per employee and kind


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.DISPLAY_TIMEZONE)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Kolkata")


# --------------------------------------------------------------------------
# access
# --------------------------------------------------------------------------

def require_reviewer(db: Session, user: User, perms: set[str], partner: Organization | None = None) -> None:
    """Reconciliation exposes who entered, cleared and moved what. Only the entry-audit levels (administrator, developer, Entry Reviewer) may open it, decided
    from the roles and permissions of THIS request (the same rule as the entry history); a platform-scoped reviewer only for their own platform."""
    sc = scope_for(db, user, perms)
    if sc.level not in (Level.ADMINISTRATOR, Level.REVIEWER) or not sc.can_view_history:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Performance reconciliation is for administrators and entry reviewers.")
    if partner is not None and sc.platform_id is not None and sc.platform_id != partner.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only reconcile your own platform.")


# --------------------------------------------------------------------------
# rebuilding a moment
# --------------------------------------------------------------------------

@dataclass
class Rec:
    """One covered store-day: the entry that made it covered."""
    entry_id: uuid.UUID
    creator_id: uuid.UUID | None
    creator_name: str | None
    verified: bool | None
    via: str | None = None                       # created_via: where it came from (android-app/..., sheet_sync_scheduled, file import, no_actor)


@dataclass
class State:
    """Everything a report depends on, at one instant."""
    partner_slug: str
    month: date
    cutoff: datetime
    today: date
    days: list[date]
    as_of: date
    scopes: dict[uuid.UUID, frozenset[uuid.UUID]]
    cover: dict[date, dict[uuid.UUID, Rec]]
    scope_basis: str                           # "live" | "stored" | "current"
    who: dict[uuid.UUID, dict] = field(default_factory=dict)

    def covered(self) -> dict[date, set[uuid.UUID]]:
        return {d: set(self.cover.get(d, {})) for d in self.days}

    def figures(self) -> dict[uuid.UUID, dict]:
        """{employee: {done, expected, percent, stores}} by the very formula of the live report (performance_service.score)."""
        cov = self.covered()
        out = {}
        for eid, stores in self.scopes.items():
            if not stores:
                continue
            _, done, expected = ps.score(set(stores), self.days, cov)
            out[eid] = {"done": done, "expected": expected, "percent": ps._pct(done, expected), "stores": len(stores)}
        return out


def _load_cover(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID, first: date, last: date, cutoff: datetime | None) -> dict[date, dict[uuid.UUID, Rec]]:
    """{day: {store: Rec}}: the store-days that had an entry at `cutoff` (None = right now, straight from order_entries). An entry exists at an instant when it was
    created by then and had not been deleted by then (deleted_rows holds the copy and the moment of every deletion; a deleted entry that was later restored is
    absent between the two)."""
    out: dict[date, dict[uuid.UUID, Rec]] = defaultdict(dict)
    if last < first:
        return out
    p = {"org": org_id, "pid": partner_id, "a": first, "b": last}
    if cutoff is None:
        rows = db.execute(text("""
            SELECT e.id, e.store_id, e.order_date, e.created_by_user_id, e.created_by_name, e.creator_verified, e.created_via
            FROM order_entries e JOIN stores s ON s.id = e.store_id
            WHERE s.organization_id = :org AND s.partner_organization_id = :pid AND e.order_date BETWEEN :a AND :b"""), p).all()
    else:
        p["cut"] = cutoff
        rows = db.execute(text("""
            SELECT e.id, e.store_id, e.order_date, e.created_by_user_id, e.created_by_name, e.creator_verified, e.created_via
            FROM order_entries e JOIN stores s ON s.id = e.store_id
            WHERE s.organization_id = :org AND s.partner_organization_id = :pid AND e.order_date BETWEEN :a AND :b AND e.created_at <= :cut
              AND NOT EXISTS (SELECT 1 FROM deleted_rows d WHERE d.table_name = 'order_entries' AND d.row_id = e.id::text
                              AND d.deleted_at <= :cut AND (d.restored_at IS NULL OR d.restored_at > :cut))
            UNION ALL
            SELECT (d.data->>'id')::uuid, (d.data->>'store_id')::uuid, (d.data->>'order_date')::date, (d.data->>'created_by_user_id')::uuid,
                   d.data->>'created_by_name', (d.data->>'creator_verified')::boolean, d.data->>'created_via'
            FROM deleted_rows d
            WHERE d.table_name = 'order_entries' AND d.deleted_at > :cut AND (d.data->>'created_at')::timestamptz <= :cut
              AND (d.data->>'order_date')::date BETWEEN :a AND :b
              AND (d.data->>'store_id')::uuid IN (SELECT id FROM stores WHERE organization_id = :org AND partner_organization_id = :pid)"""), p).all()
    for entry_id, store_id, day, uid, name, verified, via in rows:
        out[day][store_id] = Rec(entry_id, uid, name, verified, via)
    return out


def current_scopes(db: Session, org_id: uuid.UUID, partner: Organization) -> tuple[dict[uuid.UUID, frozenset[uuid.UUID]], dict[uuid.UUID, dict]]:
    employees = EmployeeRepository(db).all_for_platform(org_id, partner.id)
    scopes, _ = assignment_service.employee_store_scopes(db, partner, employees)
    who = {e.id: {"name": e.full_name, "code": e.employee_code} for e in employees}
    return {e.id: frozenset(scopes.get(e.id, [])) for e in employees}, who


def _names(db: Session, ids) -> dict[uuid.UUID, dict]:
    ids = list(ids)
    if not ids:
        return {}
    return {u.id: {"name": u.full_name, "code": u.employee_code} for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


def build_state(
    db: Session, org_id: uuid.UUID, partner: Organization, month: date, cutoff: datetime | None, *,
    scopes: dict[uuid.UUID, frozenset[uuid.UUID]] | None = None, who: dict[uuid.UUID, dict] | None = None,
) -> State:
    """The report's inputs at `cutoff` (None = now): the days judged then ("today" = the IST date of the instant; holidays play no part), the entries that
    existed then, and the stores of each employee (`scopes` when given, else today's)."""
    now = cutoff or datetime.now(timezone.utc)
    today = ps.business_today() if cutoff is None else cutoff.astimezone(_tz()).date()
    last_of_month = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    days, as_of, _ = ps.judged_days_from(month, today)
    basis = "stored" if scopes is not None else ("live" if cutoff is None else "current")
    if scopes is None:
        scopes, who = current_scopes(db, org_id, partner)
    who = {**(who or {})}
    for eid, n in _names(db, [e for e in scopes if e not in who]).items():
        who[eid] = n
    cover = _load_cover(db, org_id, partner.id, month, min(as_of, last_of_month), cutoff) if days else {}
    return State(partner.slug, month, now, today, days, as_of, scopes, cover, basis, who)


# --------------------------------------------------------------------------
# snapshots
# --------------------------------------------------------------------------

def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _snapshot_hash(partner_slug: str, month: date, generated_at: datetime, definition: str, employees: list, scopes: dict, judged_days: list) -> str:
    return _hash({"partner": partner_slug, "month": month, "at": generated_at.astimezone(timezone.utc).isoformat(), "definition": definition,
                  "employees": employees, "scopes": scopes, "days": judged_days})


def create_snapshot(
    actor_id: uuid.UUID, partner_slug: str, month: date, *, source: str, report_text: str | None = None,
    revision_of: uuid.UUID | None = None, revision_reason: str | None = None, session_factory=None,
) -> PerformanceSnapshot:
    """Record what the performance report says RIGHT NOW. Everything is read inside ONE REPEATABLE READ transaction (its own session, so the request's open
    transaction cannot interleave): every query sees the same database state, and `generated_at` is taken as the transaction's first statement, so an entry saved
    while the snapshot is being built either is in all of it or in none of it. The row is append-only; a correction of a stored report is another snapshot with
    `revision_of` + `revision_reason`."""
    from app.db.session import SessionLocal

    if source not in SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown snapshot source.")
    if revision_of is not None and not (revision_reason or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A revised report needs the reason it was revised.")
    s = (session_factory or SessionLocal)()
    try:
        s.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        generated_at = s.execute(text("SELECT clock_timestamp()")).scalar_one()          # the first statement: the transaction's data snapshot is taken here
        actor = s.get(User, actor_id)
        if actor is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
        partner = ps._partner(s, partner_slug)
        if revision_of is not None:
            orig = s.get(PerformanceSnapshot, revision_of)
            if orig is None or orig.partner_slug != partner.slug or orig.month != month or orig.organization_id != actor.organization_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "The report being revised was not found for this platform and month.")
        today = ps.business_today()
        report = ps.performance(s, actor, partner.slug, month, today, None)
        scopes, _ = current_scopes(s, actor.organization_id, partner)
        employees = [{k: v for k, v in row.items() if k != "daily"} for row in report["employees"]]
        days = [d.isoformat() for d in ps.judged_days_from(month, today)[0]]
        scopes_json = {str(e): sorted(str(x) for x in st) for e, st in scopes.items() if st}
        emp_json = jsonable_encoder(employees)
        snap = PerformanceSnapshot(
            organization_id=actor.organization_id, partner_slug=partner.slug, month=month, as_of=report["as_of"], generated_at=generated_at,
            generated_by_user_id=actor.id, generated_by_name=actor.full_name, source=source, definition_version=ps.DEFINITION_VERSION,
            judged_days=days, employees=emp_json, scopes=scopes_json, summary=jsonable_encoder(report["summary"]),
            report_text=report_text, content_hash=_snapshot_hash(partner.slug, month, generated_at, ps.DEFINITION_VERSION, emp_json, scopes_json, days),
            revision_of=revision_of, revision_reason=(revision_reason or "").strip() or None,
        )
        s.add(snap)
        s.commit()
        s.refresh(snap)
        s.expunge(snap)
        return snap
    finally:
        s.close()


def snapshot_row(snap: PerformanceSnapshot) -> dict:
    return {
        "id": snap.id, "partner_slug": snap.partner_slug, "month": f"{snap.month:%Y-%m}", "as_of": snap.as_of, "generated_at": snap.generated_at,
        "generated_by": snap.generated_by_name, "source": snap.source, "definition_version": snap.definition_version, "employees": len(snap.employees),
        "judged_days": len(snap.judged_days), "summary": snap.summary, "content_hash": snap.content_hash,
        "revision_of": snap.revision_of, "revision_reason": snap.revision_reason, "has_report_text": snap.report_text is not None,
    }


def list_snapshots(db: Session, org_id: uuid.UUID, partner_slug: str, month: date, limit: int = 100) -> list[dict]:
    rows = db.execute(
        select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id == org_id, PerformanceSnapshot.partner_slug == partner_slug, PerformanceSnapshot.month == month)
        .order_by(PerformanceSnapshot.generated_at.desc()).limit(limit)).scalars().all()
    revised = {r.revision_of for r in rows if r.revision_of}
    return [{**snapshot_row(r), "revised_by_later": r.id in revised} for r in rows]


def get_snapshot(db: Session, org_id: uuid.UUID, snapshot_id: uuid.UUID) -> PerformanceSnapshot:
    snap = db.get(PerformanceSnapshot, snapshot_id)
    if snap is None or snap.organization_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report snapshot not found.")
    return snap


def _stored_scopes(snap: PerformanceSnapshot) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    return {uuid.UUID(e): frozenset(uuid.UUID(x) for x in stores) for e, stores in snap.scopes.items()}


def _state_of_snapshot(db: Session, partner: Organization, snap: PerformanceSnapshot) -> State:
    who = {uuid.UUID(r["employee_id"]): {"name": r["employee_name"], "code": r.get("employee_code")} for r in snap.employees}
    return build_state(db, snap.organization_id, partner, snap.month, snap.generated_at, scopes=_stored_scopes(snap), who=who)


def _hash_ok(snap: PerformanceSnapshot) -> bool:
    return _snapshot_hash(snap.partner_slug, snap.month, snap.generated_at, snap.definition_version, snap.employees, snap.scopes, snap.judged_days) == snap.content_hash


def verify_snapshot(db: Session, org_id: uuid.UUID, snapshot_id: uuid.UUID) -> dict:
    """Rebuild the snapshot's figures from the records at its instant and compare them with what it stored. `reproduced` is true only when every employee's
    figure and the judged days match; a mismatch is shown, never smoothed over. (A saved snapshot is a record of what was reported; this checks that it is also
    what the underlying records say.)"""
    snap = get_snapshot(db, org_id, snapshot_id)
    partner = ps._partner(db, snap.partner_slug)
    st = _state_of_snapshot(db, partner, snap)
    rebuilt = st.figures()
    rows, ok = [], True
    for r in snap.employees:
        if r.get("no_stores"):
            continue
        eid = uuid.UUID(r["employee_id"])
        got = rebuilt.get(eid, {"done": 0, "expected": 0, "percent": 0.0, "stores": 0})
        match = got["done"] == r["done"] and got["expected"] == r["expected"]
        ok &= match
        rows.append({"employee_id": eid, "employee_name": r["employee_name"], "reported_done": r["done"], "reported_expected": r["expected"],
                     "rebuilt_done": got["done"], "rebuilt_expected": got["expected"], "difference": got["done"] - r["done"], "matches": match})
    days_ok = [d.isoformat() for d in st.days] == list(snap.judged_days)
    hash_ok = _hash_ok(snap)
    early = snap.generated_at < EVIDENCE_START
    other_def = snap.definition_version != ps.DEFINITION_VERSION
    if early or other_def:
        state = UNVERIFIABLE
    else:
        state = VERIFIED if (ok and days_ok and hash_ok) else REVIEW
    return {
        "snapshot": snapshot_row(snap), "status": state, "status_label": STATUS_LABEL[state], "reproduced": ok and days_ok, "hash_intact": hash_ok,
        "judged_days_match": days_ok, "employees": rows,
        "notes": (["Taken before deleted entries were kept (19 Oct 2026): the data of that moment cannot be rebuilt."] if early else [])
                 + ([f"Stored under counting rules '{snap.definition_version}', not today's '{ps.DEFINITION_VERSION}': the comparison above uses today's rules, so a difference is expected."] if other_def else []),
    }


# --------------------------------------------------------------------------
# comparing two moments
# --------------------------------------------------------------------------

@dataclass
class Point:
    """One side of a comparison: a stored snapshot, or an instant rebuilt from the records (None = right now)."""
    state: State
    snapshot: PerformanceSnapshot | None = None

    def reported(self, eid: uuid.UUID) -> dict | None:
        if self.snapshot is None:
            return None
        for r in self.snapshot.employees:
            if r["employee_id"] == str(eid) and not r.get("no_stores"):
                return {"done": r["done"], "expected": r["expected"], "percent": r["percent"], "stores": r["stores"]}
        return None


def point_for(db: Session, org_id: uuid.UUID, partner: Organization, month: date, *, snapshot_id: uuid.UUID | None = None, at: datetime | None = None) -> Point:
    if snapshot_id is not None:
        snap = get_snapshot(db, org_id, snapshot_id)
        if snap.partner_slug != partner.slug or snap.month != month:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That snapshot belongs to another platform or month.")
        return Point(_state_of_snapshot(db, partner, snap), snap)
    return Point(build_state(db, org_id, partner, month, at))


def _removal_evidence(db: Session, org_id: uuid.UUID, partner: Organization, t0: datetime, t1: datetime, lost: set[tuple[uuid.UUID, date]]) -> dict[tuple[uuid.UUID, date], dict]:
    """For store-days that had an entry at t0 and none at t1: what the records say happened, between the two instants. A deletion is only 'explained' when the
    history names who cleared it (a CLEARED event with a known actor); a copy in deleted_rows alone, or a clearing with no authenticated actor, proves the
    entry was deleted but not by whom. An entry moved to another date or
    store (an EDITED event that changed order_date / store_id) is explained too."""
    if not lost:
        return {}
    store_ids = {s for s, _ in lost}
    found: dict[tuple[uuid.UUID, date], dict] = {}
    deleted: dict[tuple[uuid.UUID, date], DeletedRow] = {}
    for dr in db.execute(select(DeletedRow).where(
            DeletedRow.table_name == "order_entries", DeletedRow.deleted_at > t0, DeletedRow.deleted_at <= t1,
            DeletedRow.data["store_id"].astext.in_([str(s) for s in store_ids]))).scalars():
        try:
            key = (uuid.UUID(dr.data["store_id"]), date.fromisoformat(dr.data["order_date"]))
        except (KeyError, ValueError):
            continue
        if key in lost:
            deleted[key] = dr
    ids = []
    for dr in deleted.values():
        try:
            ids.append(uuid.UUID(dr.row_id))
        except (TypeError, ValueError):
            pass
    cleared = {}
    if ids:
        for ev in db.execute(select(OrderEntryEvent).where(OrderEntryEvent.entry_id.in_(ids), OrderEntryEvent.event_type == "CLEARED").order_by(OrderEntryEvent.created_at)).scalars():
            cleared[ev.entry_id] = ev
    stores = {s.id: s for s in db.execute(select(Store).where(Store.id.in_(list(store_ids)))).scalars()}
    for key, dr in deleted.items():
        ev = cleared.get(uuid.UUID(dr.row_id)) if dr.row_id else None
        st = stores.get(key[0])
        found[key] = {
            "kind": "cleared" if ev is not None else "deleted", "entry_id": dr.row_id, "store_id": key[0], "store_code": st.external_code if st else None,
            "store_name": st.name if st else None, "date": key[1], "at": dr.deleted_at, "by": ev.actor_name if ev else None, "by_role": ev.actor_role if ev else None,
            "source": ev.source if ev else None, "reason": (ev.reason or None) if ev else None, "reason_recorded": bool(ev and (ev.reason or "").strip()),
            "explained": bool(ev is not None and ev.actor_known),
        }
    # moved entries (the date or the store of an entry was edited): the old place lost it, the new one gained it
    for ev in db.execute(select(OrderEntryEvent).where(
            OrderEntryEvent.event_type == "EDITED", OrderEntryEvent.created_at > t0, OrderEntryEvent.created_at <= t1, OrderEntryEvent.store_id.in_(list(store_ids)),
            or_(OrderEntryEvent.new_values.has_key("order_date"), OrderEntryEvent.new_values.has_key("store_id")))).scalars():
        old = ev.old_values or {}
        try:
            key = (uuid.UUID(old.get("store_id") or str(ev.store_id)), date.fromisoformat(old["order_date"]))
        except (KeyError, ValueError, TypeError):
            continue
        if key in lost and key not in found:
            st = stores.get(key[0])
            found[key] = {"kind": "moved", "entry_id": ev.entry_id, "store_id": key[0], "store_code": st.external_code if st else None, "store_name": st.name if st else None,
                          "date": key[1], "at": ev.created_at, "by": ev.actor_name, "by_role": ev.actor_role, "source": ev.source, "reason": ev.reason or None,
                          "reason_recorded": bool((ev.reason or "").strip()), "explained": bool(ev.actor_known)}
    return found


def _store_info(db: Session, ids) -> dict[uuid.UUID, dict]:
    ids = list(ids)
    if not ids:
        return {}
    return {s.id: {"store_id": s.id, "store_code": s.external_code, "store_name": s.name, "status": s.status} for s in db.execute(select(Store).where(Store.id.in_(ids))).scalars()}


def _breakdown(rec: Rec, eid: uuid.UUID) -> str:
    if rec.creator_id == eid:
        return "the employee themselves"
    if not rec.verified:
        return "older data (creator not recorded)"
    return rec.creator_name or "someone else"


def compare(db: Session, org_id: uuid.UUID, partner: Organization, month: date, prev: Point, curr: Point, employee_id: uuid.UUID | None = None) -> dict:
    """Why did each employee's figure change between `prev` and `curr`? See the module docstring for the exact split. Read-only."""
    a, b = prev.state, curr.state
    if a.cutoff > b.cutoff:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The earlier report must come first.")
    DA, DB = set(a.days), set(b.days)
    ca, cb = a.covered(), b.covered()
    ids = [e for e in {*a.scopes, *b.scopes} if employee_id is None or e == employee_id]
    figs_a, figs_b = a.figures(), b.figures()
    who = {**a.who, **b.who}
    added_days = sorted(DB - DA)          # days that finished between the two moments (the same month, so none can disappear)
    common = sorted(DA & DB)

    # one pass to find every store-day that lost its entry, so the evidence is fetched once
    lost_all: set[tuple[uuid.UUID, date]] = set()
    plan: dict[uuid.UUID, dict] = {}
    for eid in ids:
        S1, S2 = set(a.scopes.get(eid, ())), set(b.scopes.get(eid, ()))
        lost = [(s, d) for d in common for s in (S2 & ca[d]) - cb[d]]
        lost_all.update(lost)
        plan[eid] = {"S1": S1, "S2": S2, "lost": lost}
    evidence = _removal_evidence(db, org_id, partner, a.cutoff, b.cutoff, lost_all)
    store_cache = _store_info(db, set().union(*(p["S1"] ^ p["S2"] for p in plan.values())) if plan else set())
    early = a.cutoff < EVIDENCE_START
    notes = []
    if a.scope_basis == "current" or b.scope_basis == "current":
        notes.append("Who was in each employee's scope at that moment is not recorded by the application, so today's scope is used for the moment(s) rebuilt from the records. "
                     "A change of scope in between would show here as a difference it cannot name. Stored snapshots keep their own store lists.")
    if early:
        notes.append("The earlier moment is before deleted entries were kept (19 Oct 2026): entries deleted before then cannot be seen, so this comparison cannot be verified.")

    rows = []
    for eid in ids:
        S1, S2, lost = plan[eid]["S1"], plan[eid]["S2"], plan[eid]["lost"]
        rec_a, rec_b = figs_a.get(eid), figs_b.get(eid)
        if rec_a is None and rec_b is None:
            continue
        rec_a = rec_a or {"done": 0, "expected": 0, "percent": 0.0, "stores": 0}
        rec_b = rec_b or {"done": 0, "expected": 0, "percent": 0.0, "stores": 0}
        new_days = sum(len(S2 & cb[d]) for d in added_days)
        gained = sum(len((S2 - S1) & ca[d]) for d in common)
        lost_scope = sum(len((S1 - S2) & ca[d]) for d in common)
        added_pairs = [(s, d) for d in common for s in (S2 & cb[d]) - ca[d]]
        explained_removed = [evidence[k] for k in lost if k in evidence and evidence[k]["explained"]]
        unexplained_removed = [k for k in lost if k not in evidence or not evidence[k]["explained"]]
        recon_delta = rec_b["done"] - rec_a["done"]
        parts = new_days + gained - lost_scope + len(added_pairs) - len(lost)
        gap = recon_delta - parts            # the split is an arithmetic identity, so this is 0; were it ever not, the row says so instead of the page failing
        rep_a, rep_b = prev.reported(eid), curr.reported(eid)
        reported_delta = (rep_b["done"] if rep_b else rec_b["done"]) - (rep_a["done"] if rep_a else rec_a["done"])
        residual = reported_delta - recon_delta                                # what a stored figure says beyond what the records reproduce
        unexplained_total = len(unexplained_removed) + abs(residual) + abs(gap)
        decreasing = lost_scope + len(lost)
        reasons = []
        if new_days:
            reasons.append(f"{new_days} store-days came from the newly finished day(s)")
        if added_pairs:
            reasons.append(f"{len(added_pairs)} entries were added to earlier days")
        if lost:
            reasons.append(f"{len(lost)} store-days lost their entry ({len(explained_removed)} with a recorded clearing event)")
        if lost_scope or gained:
            reasons.append(f"stores changed hands: +{gained} / -{lost_scope} store-days")
        if residual:
            reasons.append(f"the stored figure differs from what the records reproduce by {residual:+d}")
        if gap:
            reasons.append(f"the causes above do not add up to the change (off by {gap:+d}); this is a calculation fault to report")
        if unexplained_removed:
            reasons.append(f"{len(unexplained_removed)} lost store-days have no clearing event naming who removed them")
        if early:
            state = UNVERIFIABLE
        elif unexplained_total:
            state = REVIEW
        elif decreasing:
            state = RECONCILED
        else:
            state = VERIFIED
        attribution, via = Counter(), Counter()
        for d in b.days:
            for s in S2 & set(b.cover.get(d, {})):
                attribution[_breakdown(b.cover[d][s], eid)] += 1
                via[b.cover[d][s].via or "not recorded"] += 1
        added_by = Counter(_breakdown(b.cover[d][s], eid) for s, d in added_pairs)
        info = who.get(eid, {})
        rows.append({
            "employee_id": eid, "employee_name": info.get("name"), "employee_code": info.get("code"),
            "previous": {**rec_a, "reported": rep_a is not None}, "current": {**rec_b, "reported": rep_b is not None},
            "delta": rec_b["done"] - rec_a["done"] if not (rep_a and rep_b) else reported_delta,
            "change_percent": round((rec_b["done"] - rec_a["done"]) * 100 / rec_a["done"], 2) if rec_a["done"] else None,
            "percent_points": round(rec_b["percent"] - rec_a["percent"], 1),
            "explained": {
                "new_days": new_days, "entries_added": len(added_pairs), "entries_removed": len(lost) - len(unexplained_removed), "stores_gained": gained, "stores_lost": lost_scope,
            },
            "unexplained": {"removed_without_evidence": len(unexplained_removed), "stored_figure_difference": residual, "arithmetic_gap": gap, "total": unexplained_total},
            "added_by": dict(added_by), "covered_by": dict(attribution), "covered_via": dict(via),
            "records": {
                "removed": sorted((evidence[k] for k in lost if k in evidence), key=lambda r: (r["date"], str(r["store_id"])))[:MAX_RECORDS],
                "removed_without_evidence": [{"store_id": s, "store_code": (store_cache.get(s) or {}).get("store_code"), "date": d} for s, d in sorted(unexplained_removed, key=lambda x: (x[1], str(x[0])))[:MAX_RECORDS]],
                "stores_gained": [store_cache[s] for s in sorted(S2 - S1, key=str) if s in store_cache][:MAX_RECORDS],
                "stores_lost": [store_cache[s] for s in sorted(S1 - S2, key=str) if s in store_cache][:MAX_RECORDS],
            },
            "status": state, "status_label": STATUS_LABEL[state], "reasons": reasons,
        })
    rows.sort(key=lambda r: (-_SEVERITY[r["status"]], r["delta"], (r["employee_name"] or "").lower()))
    worst = max((r["status"] for r in rows), key=lambda s: _SEVERITY[s], default=VERIFIED)
    counts = Counter(r["status"] for r in rows)
    def side(p: Point) -> dict:
        s = p.state
        return {"at": s.cutoff, "snapshot_id": p.snapshot.id if p.snapshot else None, "source": "snapshot" if p.snapshot else "rebuilt from the records",
                "snapshot_source": p.snapshot.source if p.snapshot else None, "today": s.today, "as_of": s.as_of if s.days else None, "judged_days": len(s.days),
                "scope_basis": s.scope_basis, "revision_of": p.snapshot.revision_of if p.snapshot else None,
                "revision_reason": p.snapshot.revision_reason if p.snapshot else None}
    return {
        "partner_slug": partner.slug, "partner_label": partner.name, "month": f"{month:%Y-%m}", "definition": ps.DEFINITION,
        "previous": side(prev), "current": side(curr), "notes": notes,
        "summary": {"status": worst, "status_label": STATUS_LABEL[worst], "employees": len(rows), "verified": counts[VERIFIED], "reconciled": counts[RECONCILED],
                    "requires_review": counts[REVIEW], "unverifiable": counts[UNVERIFIABLE], "unexplained_total": sum(r["unexplained"]["total"] for r in rows)},
        "employees": rows,
    }
