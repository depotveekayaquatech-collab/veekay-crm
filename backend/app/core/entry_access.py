"""The ONE place that decides who may see and change which entries. Routes and services ask this module; nothing re-implements the rules.

Four levels (the names are generic on purpose):

  Level 1  Entry Contributor  (role `employee`)   own entries only; may create; never edits or deletes a submitted entry.
  Level 2  Team Lead          (role `team_lead`, permission entries.team)
                              own entries + the entries created by people who report to them; may correct those (with a reason), see their history.
  Level 3  Entry Reviewer     (role `entry_reviewer`, permissions entries.audit + entries.review)
                              every entry in their scope (the whole organisation, or one platform if the account has one); reads full history;
                              edits and finalises entries (an edit is final), reviews an entry directly without waiting for the Team Lead,
                              asks the Team Lead to check one, flags entries; can NOT change the creator or the history.
  Level 4  Administrator      (role `admin`, and the developer)
                              everything, including Store Audit and corrections, and everything Level 3 can do; still cannot rewrite history
                              (the database refuses).

Verification state of an entry (order_entries.verification_status, moved by the database triggers of migration 0053):
  submitted (L1) -> verified_l2 (Team Lead) -> reviewed_l3 (Reviewer). A Team Lead acts only on `submitted` entries; a Reviewer / administrator acts on any.

Scope is derived from the authenticated user and the permissions re-read from the database on every request, so a role change applies on the very
next call. Creator ids, roles and scopes are never read from a request body.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, DEVELOPER
from app.models.order_entry import OrderEntry
from app.models.user import User

TEAM_LEAD_ROLE = "team_lead"
REVIEWER_ROLE = "entry_reviewer"

STATUS_SUBMITTED = "submitted"
STATUS_VERIFIED = "verified_l2"
STATUS_REVIEWED = "reviewed_l3"

PERM_TEAM = "entries.team"
PERM_AUDIT = "entries.audit"
PERM_REVIEW = "entries.review"
# There is no per-person permission for these two any more (migration 0061): every Level 1 employee has both, see is_level_one().
#   - SEE every entry of the stores they can mark (the calendar numbers and the month's bottles). No history, no Store Audit.
#   - CHANGE or clear ANY entry of the stores they mark, whoever entered it or changed it last, in the dates still open to them (this month, and last month for the
#     first days of the next). Every change is audited like any correction: stamped with who made it, the earlier number kept. Outside those dates nothing changes.


class Level(StrEnum):
    CONTRIBUTOR = "entry_contributor"
    TEAM_LEAD = "team_lead"
    REVIEWER = "entry_reviewer"
    ADMINISTRATOR = "administrator"


# How senior the person who SET a number was (their role at that time, stamped on the entry). Someone sees their own numbers, and the numbers set
# by anyone strictly more senior than themselves (read-only): a contributor sees what a Team Lead, reviewer, administrator or the developer entered.
# People at the same level never see each other's numbers.
LEVEL_LABEL = {
    Level.CONTRIBUTOR: "L1 Employee", Level.TEAM_LEAD: "L2 Team Lead", Level.REVIEWER: "L3 Entry Reviewer", Level.ADMINISTRATOR: "L4 Administrator",
}
ROLE_RANK = {
    "entry_contributor": 1, "accountant": 1, "partner": 1, "unknown": 0,
    "team_lead": 2,
    "entry_reviewer": 3, "custom_admin": 3,
    "administrator": 4, "developer": 4,
}
LEVEL_RANK = {Level.CONTRIBUTOR: 1, Level.TEAM_LEAD: 2, Level.REVIEWER: 3, Level.ADMINISTRATOR: 4}


def is_level_one(db, user) -> bool:
    """A field employee at Level 1 (the employee role, and nothing above it). Re-read from the database on every call, like every permission."""
    return "employee" in _roles(db, user) and viewer_rank(db, user) == 1


def sees_every_entry(db, user) -> bool:
    """Every Level 1 employee sees their colleagues' numbers for the stores they can mark (read-only)."""
    return is_level_one(db, user)


def can_edit_any_entry(db, user) -> bool:
    """Every Level 1 employee may change or clear any entry of their stores in the dates still open to them (this month, and last month for the first days of the
    next), whoever entered it. The dates are enforced where the change is made; the audit stamps who did it and keeps the earlier number."""
    return is_level_one(db, user)


def roles_above(rank: int) -> list[str]:
    return [r for r, k in ROLE_RANK.items() if k > rank]


def viewer_rank(db, user) -> int:
    """How senior the viewer is, from their roles (the same ladder as the four levels)."""
    codes = _roles(db, user)
    if codes & {ADMIN, DEVELOPER}:
        return 4
    if codes & {REVIEWER_ROLE, "manager"}:
        return 3
    if TEAM_LEAD_ROLE in codes:
        return 2
    return 1


def higher_clause(rank: int):
    """SQL for "the current number was set by someone more senior than `rank`, and is a plain number" (never a row carrying a developer's cash adjustment,
    which stays the developer's business). Author = the last person who changed the number, else its creator; an old entry whose creator is unknown
    but whose number was last set by an administrator counts as the administrator's."""
    author = case((OrderEntry.last_modified_at.is_not(None), OrderEntry.last_modified_by_role), else_=OrderEntry.created_by_role)
    legacy_admin = and_(OrderEntry.creator_verified.is_(False), OrderEntry.last_modified_at.is_(None), OrderEntry.source == "admin")
    return and_(OrderEntry.cash_adjustment == 0, or_(author.in_(roles_above(rank)), legacy_admin if rank < 4 else False))


def visible_clause(ids, rank: int):
    """SQL for "this person may see the number": it is theirs, or it was set by someone more senior."""
    return or_(owned_clause(ids), higher_clause(rank))


def set_by_someone_above(entry: OrderEntry, rank: int) -> bool:
    """The Python twin of higher_clause."""
    if entry.cash_adjustment:
        return False
    author = entry.last_modified_by_role if entry.last_modified_at is not None else entry.created_by_role
    if ROLE_RANK.get(author or "", 0) > rank:
        return True
    return rank < 4 and not entry.creator_verified and entry.last_modified_at is None and entry.source == "admin"


def owned_clause(ids):
    """SQL for "the number on this entry was entered by one of `ids`" (the same rule as owns_value, for queries)."""
    ids = list(ids)
    return or_(
        OrderEntry.created_by_user_id.in_(ids),
        and_(OrderEntry.source == "employee", OrderEntry.marked_by_user_id.in_(ids), OrderEntry.last_modified_by_user_id.in_(ids)),
    )


def owns_value(entry: OrderEntry, ids) -> bool:
    """True when the number on this entry was entered by someone in `ids`: they created it, or they entered the employee's number on a day a developer's
    cash adjustment had created first (the creator then stays the developer; the employee is the modifier and the marker)."""
    if entry.created_by_user_id in ids:
        return True
    return entry.source == "employee" and entry.marked_by_user_id in ids and entry.last_modified_by_user_id in ids


@dataclass(frozen=True)
class EntryScope:
    level: Level
    organization_id: uuid.UUID
    user_id: uuid.UUID
    creator_ids: frozenset[uuid.UUID] | None      # whose entries are in scope (None = everyone's, within the organisation / platform)
    platform_id: uuid.UUID | None                 # restricts everything to one platform's stores (a platform-scoped reviewer)
    can_view_history: bool
    can_edit_values: bool
    can_review: bool
    can_store_audit: bool
    can_verify: bool = False              # Level 2: verify the `submitted` entries of the team
    can_request_check: bool = False       # Level 3 / 4: ask the Team Lead to check a `submitted` entry

    def conditions(self) -> list:
        """SQL conditions on OrderEntry that keep only what this user may see. Add them to EVERY query that returns entries."""
        out = [OrderEntry.organization_id == self.organization_id]
        if self.creator_ids is not None:
            out.append(owned_clause(self.creator_ids))
        return out

    def allows(self, entry: OrderEntry, store_platform_id: uuid.UUID | None = None) -> bool:
        if entry.organization_id != self.organization_id:
            return False
        if self.platform_id is not None and store_platform_id != self.platform_id:
            return False
        return self.creator_ids is None or owns_value(entry, self.creator_ids)

    def can_edit(self, entry: OrderEntry, store_platform_id: uuid.UUID | None = None) -> bool:
        """Values may be corrected where the creator is known; a legacy / unverified entry (no creator on record) is left to a reviewer or an
        administrator, who may use their own knowledge. A Team Lead only changes an entry that is still `submitted`."""
        if not self.can_edit_values or not self.allows(entry, store_platform_id):
            return False
        if self.level is Level.TEAM_LEAD:
            return entry.creator_verified and entry.verification_status == STATUS_SUBMITTED
        return True

    def can_verify_entry(self, entry: OrderEntry, store_platform_id: uuid.UUID | None = None) -> bool:
        return self.can_verify and self.allows(entry, store_platform_id) and entry.verification_status == STATUS_SUBMITTED

    def can_finalise(self, entry: OrderEntry, store_platform_id: uuid.UUID | None = None) -> bool:
        """Reviewer / administrator: mark the entry Reviewed directly (the Team Lead is no longer needed)."""
        return self.can_review and self.allows(entry, store_platform_id) and entry.verification_status != STATUS_REVIEWED

    def can_request_check_of(self, entry: OrderEntry, store_platform_id: uuid.UUID | None = None) -> bool:
        return self.can_request_check and self.allows(entry, store_platform_id) and entry.verification_status == STATUS_SUBMITTED


def _roles(db: Session, user: User) -> set[str]:
    from app.repositories.user_repository import UserRepository

    return set(UserRepository(db).get_role_codes(user.id))


def team_ids(db: Session, lead: User) -> frozenset[uuid.UUID]:
    reports = db.execute(
        select(User.id).where(User.reports_to_user_id == lead.id, User.organization_id == lead.organization_id)
    ).scalars().all()
    return frozenset({lead.id, *reports})


def scope_for(db: Session, user: User, perms: set[str]) -> EntryScope:
    """The user's entry scope. Highest level wins; permissions are the permissions of THIS request (re-derived from the database)."""
    roles = _roles(db, user)
    if roles & {ADMIN, DEVELOPER}:
        return EntryScope(Level.ADMINISTRATOR, user.organization_id, user.id, None, None, True, True, True, True, can_request_check=True)
    if PERM_AUDIT in perms:
        can_review = PERM_REVIEW in perms
        return EntryScope(Level.REVIEWER, user.organization_id, user.id, None, user.platform_organization_id,
                          True, can_review, can_review, True, can_request_check=can_review)
    if PERM_TEAM in perms:
        return EntryScope(Level.TEAM_LEAD, user.organization_id, user.id, team_ids(db, user), None, True, True, False, False, can_verify=True)
    return EntryScope(Level.CONTRIBUTOR, user.organization_id, user.id, frozenset({user.id}), None, False, False, False, False)


def team_only(db: Session, user: User, perms: set[str]) -> frozenset[uuid.UUID] | None:
    """For a Team Lead: the people they may look at (themselves and who reports to them), for views of PEOPLE (attendance, leave) rather than entries.
    None for everyone else: those views are then governed by their own permission as before."""
    scope = scope_for(db, user, perms)
    return scope.creator_ids if scope.level is Level.TEAM_LEAD else None


def level_label(db: Session, user: User, perms: set[str]) -> str:
    """The level as people read it: "L1 Employee", "L2 Team Lead", "L3 Entry Reviewer", "L4 Administrator" (the developer is "L4 Developer")."""
    if DEVELOPER in _roles(db, user):
        return "L4 Developer"
    return LEVEL_LABEL[level_of(db, user, perms)]


def level_of(db: Session, user: User, perms: set[str]) -> Level:
    return scope_for(db, user, perms).level
