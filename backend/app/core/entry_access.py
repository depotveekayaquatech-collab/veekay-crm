"""The ONE place that decides who may see and change which entries. Routes and services ask this module; nothing re-implements the rules.

Four levels (the names are generic on purpose):

  Level 1  Entry Contributor  (role `employee`)   own entries only; may create; never edits or deletes a submitted entry.
  Level 2  Team Lead          (role `team_lead`, permission entries.team)
                              own entries + the entries created by people who report to them; may correct those (with a reason), see their history.
  Level 3  Entry Reviewer     (role `entry_reviewer`, permissions entries.audit + entries.review)
                              every entry in their scope (the whole organisation, or one platform if the account has one); reads full history;
                              marks reviewed / flagged; can NOT change a value, the creator or the history.
  Level 4  Administrator      (role `admin`, and the developer)
                              everything, including Store Audit and corrections; still cannot rewrite history (the database refuses).

Scope is derived from the authenticated user and the permissions re-read from the database on every request, so a role change applies on the very
next call. Creator ids, roles and scopes are never read from a request body.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, DEVELOPER
from app.models.order_entry import OrderEntry
from app.models.user import User

TEAM_LEAD_ROLE = "team_lead"
REVIEWER_ROLE = "entry_reviewer"

PERM_TEAM = "entries.team"
PERM_AUDIT = "entries.audit"
PERM_REVIEW = "entries.review"


class Level(StrEnum):
    CONTRIBUTOR = "entry_contributor"
    TEAM_LEAD = "team_lead"
    REVIEWER = "entry_reviewer"
    ADMINISTRATOR = "administrator"


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
        """Values may be corrected only where the creator is known (a legacy / unverified entry is the administrators' to investigate)."""
        if not self.can_edit_values or not self.allows(entry, store_platform_id):
            return False
        return self.level is Level.ADMINISTRATOR or entry.creator_verified


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
        return EntryScope(Level.ADMINISTRATOR, user.organization_id, user.id, None, None, True, True, True, True)
    if PERM_AUDIT in perms:
        return EntryScope(Level.REVIEWER, user.organization_id, user.id, None, user.platform_organization_id,
                          True, False, PERM_REVIEW in perms, True)
    if PERM_TEAM in perms:
        return EntryScope(Level.TEAM_LEAD, user.organization_id, user.id, team_ids(db, user), None, True, True, False, False)
    return EntryScope(Level.CONTRIBUTOR, user.organization_id, user.id, frozenset({user.id}), None, False, False, False, False)


def level_of(db: Session, user: User, perms: set[str]) -> Level:
    return scope_for(db, user, perms).level
