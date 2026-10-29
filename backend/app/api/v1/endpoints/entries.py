"""Entry ownership, history, correction and review — for Team Leads (their team), Entry Reviewers and administrators (Store Audit).
Every route derives the caller's scope from the authenticated user (core.entry_access); an id outside the scope answers 404 and is logged."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.entry import EntryCheckRequest, EntryComment, EntryEdit, EntryReview, EntryVerify, StoreVerify, TeamAssign
from app.services import entry_service

router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("/search")
def search(
    response: Response,
    entry_id: uuid.UUID | None = None, store_id: uuid.UUID | None = None, store: str | None = Query(None, max_length=100),
    outlet_id: str | None = Query(None, max_length=64), platform: str | None = Query(None, max_length=32),
    creator: str | None = Query(None, max_length=100), creator_id: uuid.UUID | None = None, creator_role: str | None = Query(None, max_length=40),
    modifier: str | None = Query(None, max_length=100), team_lead: str | None = Query(None, max_length=100),
    date_from: date | None = None, date_to: date | None = None,
    created_from: str | None = Query(None, max_length=40), created_to: str | None = Query(None, max_length=40),
    review_status: str | None = Query(None, pattern="^(none|reviewed|flagged|needs_correction)$"),
    verification: str | None = Query(None, pattern="^(pending_l2|verified_l2|reviewed_l3|requested)$"),
    edited: bool | None = None, flagged: bool | None = None, unverified: bool | None = None,
    failed_sync: bool | None = None, duplicate_attempts: bool | None = None, deleted: bool | None = None,
    source: str | None = Query(None, max_length=60),
    page: int = 1, page_size: int = 25,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Server-side, paginated, combinable search over the entries the caller may see (a Team Lead: their team; a reviewer / administrator: Store Audit)."""
    response.headers["Cache-Control"] = "no-store"
    f = {k: v for k, v in locals().items() if k in {
        "entry_id", "store_id", "store", "outlet_id", "platform", "creator", "creator_id", "creator_role", "modifier", "team_lead", "date_from",
        "date_to", "created_from", "created_to", "review_status", "verification", "edited", "flagged", "unverified", "failed_sync", "duplicate_attempts", "deleted",
        "source"} and v is not None}
    return entry_service.search(db, user, perms, f, page, page_size)


@router.get("/attempts")
def attempts(
    response: Response, store_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None, store: str | None = Query(None, max_length=100),
    outcome: str | None = Query(None, pattern="^(saved|rejected|duplicate)$"), date_from: date | None = None, date_to: date | None = None,
    page: int = 1, page_size: int = 25,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Every attempt to mark an entry, saved or not: refused attempts and repeated submissions (Store Audit)."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.attempts(db, user, perms, store_id=store_id, user_id=user_id, store=store, outcome=outcome, date_from=date_from, date_to=date_to,
                                  page=page, page_size=page_size)


@router.get("/security-events")
def security_events(
    response: Response, event_type: str | None = Query(None, max_length=60), page: int = 1, page_size: int = 25,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return entry_service.security_events(db, user, perms, event_type=event_type, page=page, page_size=page_size)


@router.get("/options")
def options(
    response: Response, kind: str = Query(..., pattern="^(platform|store|person)$"), q: str | None = Query(None, max_length=100), limit: int = Query(20, ge=1, le=300),
    platform_id: uuid.UUID | None = None,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[dict]:
    """Pickers for the Partner, Store-wise and Employee-wise filters, always inside the caller's own scope. `platform_id` narrows the employees to one partner."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.filter_options(db, user, perms, kind, q, limit, platform_id)


@router.get("/team-overview")
def team_overview(
    response: Response, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Team Lead dashboard: people, stores covered, bottles (this month and today), entries by state, and one row per team member."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.team_overview(db, user, perms)


@router.get("/employee-stores")
def employee_stores(
    response: Response, creator_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
    store: str | None = Query(None, max_length=100), platform: str | None = Query(None, max_length=32),
    verification: str | None = Query(None, pattern="^(pending_l2|verified_l2|reviewed_l3|requested)$"),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """One row per store with the number of entries in each state, for one employee when `creator_id` is given, else for everything in the caller's scope."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.employee_stores(db, user, perms, creator_id, {"date_from": date_from, "date_to": date_to, "verification": verification, "store": store, "platform": platform})


@router.get("/hierarchy")
def hierarchy(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Administrators: per platform, who reviews, which Team Leads there are, who reports to whom, and who has no Team Lead yet."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.hierarchy(db, user)


@router.post("/assign-team")
def assign_team(payload: TeamAssign, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Administrators: put several employees under one Team Lead at once."""
    return entry_service.assign_team(db, user, payload.team_lead_id, payload.employee_ids)


@router.get("/store-review")
def store_review(
    response: Response, store_id: uuid.UUID, creator_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
    year: int | None = Query(None, ge=2000, le=2100), month: int | None = Query(None, ge=1, le=12),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """One store opened for checking: details and contacts, a month of its entries as a calendar, and the counts per verification state."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.store_review(db, user, perms, store_id, {"creator_id": creator_id, "date_from": date_from, "date_to": date_to, "year": year, "month": month})


@router.post("/verify-store")
def verify_store(
    payload: StoreVerify,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Verify a whole store at once (Team Lead: its `submitted` entries; Reviewer / administrator: everything not yet reviewed). Flagged entries are skipped."""
    return entry_service.verify_store(db, user, perms, payload.store_id, {"creator_id": payload.creator_id, "date_from": payload.date_from, "date_to": payload.date_to}, payload.comment)


@router.get("/summary")
def summary(
    response: Response, days: int = Query(30, ge=1, le=366),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Entries per verification state (pending Team Lead, verified, reviewed, verification requested) in the caller's scope."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.summary(db, user, perms, days)


@router.get("/leads")
def leads(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return entry_service.team_leads(db, user)


@router.get("/team")
def team(perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return entry_service.team_members(db, user, perms)


@router.get("/changes-by-employee")
def changes_by_employee(
    response: Response, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), platform: str | None = Query(None, max_length=32),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Audit log: for each person who entered numbers, how many of their entries (on the dates of the month) were never changed, changed once, or changed more than once."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.changes_by_employee(db, user, perms, month, platform)


@router.get("/changes-by-employee/{creator_id}")
def changed_entries_of(
    response: Response, creator_id: uuid.UUID, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), kind: str = Query("changed", pattern="^(changed|once|multiple)$"),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """The entries of one person that were changed after they entered them: first number, number now, how many changes, who changed it last."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.changed_entries_of(db, user, perms, creator_id, month, kind)


@router.get("/{entry_id}")
def entry_detail(
    entry_id: uuid.UUID, response: Response,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """One entry with its complete history (a removed entry too), oldest event first."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.timeline(db, user, perms, entry_id)


@router.patch("/{entry_id}")
def edit_entry(
    entry_id: uuid.UUID, payload: EntryEdit,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Correct an entry. A reason is required and the version you saw must still be current (409 otherwise)."""
    return entry_service.edit_entry(db, user, perms, entry_id, payload.bottle_count, payload.reason, payload.expected_version)


@router.post("/{entry_id}/review")
def review_entry(
    entry_id: uuid.UUID, payload: EntryReview,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    return entry_service.review_entry(db, user, perms, entry_id, payload.action, payload.comment)


@router.post("/{entry_id}/verify")
def verify_entry(
    entry_id: uuid.UUID, payload: EntryVerify,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Level 2: verify a Submitted entry of your team (409 if it is no longer Submitted)."""
    return entry_service.verify_entry(db, user, perms, entry_id, payload.comment)


@router.post("/{entry_id}/request-check")
def request_check(
    entry_id: uuid.UUID, payload: EntryCheckRequest,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Level 3 / 4: ask the Team Lead to check a Submitted entry (creates the pending request and notifies them)."""
    return entry_service.request_check(db, user, perms, entry_id, payload.note)


@router.post("/{entry_id}/comments")
def add_comment(
    entry_id: uuid.UUID, payload: EntryComment,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Add a comment to the entry's history."""
    return entry_service.add_comment(db, user, perms, entry_id, payload.text)
