"""Entry ownership, history, correction and review — for Team Leads (their team), Entry Reviewers and administrators (Store Audit).
Every route derives the caller's scope from the authenticated user (core.entry_access); an id outside the scope answers 404 and is logged."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.entry import EntryCheckRequest, EntryComment, EntryEdit, EntryReview, EntryVerify
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
    response: Response, kind: str = Query(..., pattern="^(store|person)$"), q: str | None = Query(None, max_length=100), limit: int = Query(20, ge=1, le=50),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[dict]:
    """Typeahead for the Store-wise and Employee-wise filters, always inside the caller's own scope."""
    response.headers["Cache-Control"] = "no-store"
    return entry_service.filter_options(db, user, perms, kind, q, limit)


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
