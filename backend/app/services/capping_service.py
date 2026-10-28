"""
Zepto capping: how many bottles each store may take per day. This module only decides WHO may use it; the capping itself (its history, changing it) is
capping_history_service.

Who may use it (always re-checked on the server, whatever the app shows):
  * every ACTIVE employee whose platform is Zepto, whatever their state or region,
  * the Zepto partner login (the platform's own account), and
  * administrators (they hold orders.correct and belong to no platform), so the Capping page works for them too.
  Blinkit employees and Blinkit partner logins (whatever else they hold) are refused. Changing a capping needs capping.change on top (see capping_history_service).
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationKind
from app.models.user import User

PLATFORM = "zepto"
MAX_CAP = 1_000_000      # the largest daily capping accepted


def is_eligible(user: User, perms: set[str]) -> bool:
    """Active Zepto employee or partner login, or an administrator. Never anyone on another platform."""
    if not user.is_active:
        return False
    slug = ((user.platform_organization.slug if user.platform_organization is not None else None) or "").strip().lower()
    if slug == PLATFORM:
        return True
    # Administrators (they hold orders.correct and belong to no platform). Someone who works on another platform (a Blinkit Team Lead, say) never sees Zepto
    # capping, even if "correct any entry" was ticked for them.
    return "orders.correct" in perms and not slug


def require_eligible(user: User, perms: set[str]) -> None:
    if not is_eligible(user, perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capping is available to Zepto employees.")


def _partner(db: Session, org_id: uuid.UUID) -> Organization:
    p = db.execute(select(Organization).where(Organization.slug == PLATFORM, Organization.kind == OrganizationKind.PARTNER.value)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zepto is not set up in the CRM.")
    return p
