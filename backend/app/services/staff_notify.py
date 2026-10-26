"""
Notifications for Veekay employees and admins: an in-app feed entry per person, and a push message to their registered
phones when Firebase is configured. Callers add this inside their own transaction.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.external_activity import StaffDevice, StaffNotification
from app.models.permission import Permission, RolePermission
from app.models.role import Role
from app.models.user import User, UserRole
from app.models.user_permission import UserPermission
from app.services import external_notify


def users_with_permission(db: Session, org_id: uuid.UUID, code: str) -> list[uuid.UUID]:
    """Active people of the organisation who hold a permission: admins and developers hold every ordinary one, other
    roles hold what they were given, and a person may also have it granted directly."""
    everything = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code.in_(("admin", "developer")))
    via_role = (
        select(UserRole.user_id).join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id).where(Permission.code == code)
    )
    direct = select(UserPermission.user_id).join(Permission, Permission.id == UserPermission.permission_id).where(Permission.code == code)
    ids = set(db.execute(everything).scalars()) | set(db.execute(via_role).scalars()) | set(db.execute(direct).scalars())
    if not ids:
        return []
    return list(db.execute(
        select(User.id).where(User.id.in_(ids), User.organization_id == org_id, User.is_active.is_(True))
    ).scalars())


def ticket_audience(db: Session, store) -> list[uuid.UUID]:
    """Who hears about a new ticket for this store: whoever manages tickets, and the employees who handle the store (if they can open tickets)."""
    from app.services import assignment_service

    can_open = set(users_with_permission(db, store.organization_id, "tickets.view"))
    handlers = [u.id for u in assignment_service.employees_covering_store(db, store) if u.id in can_open]
    return list(dict.fromkeys([*users_with_permission(db, store.organization_id, "tickets.manage"), *handlers]))


def notify_users(
    db: Session, user_ids: list[uuid.UUID], *, kind: str, title: str, body: str, ref_id: uuid.UUID | str | None = None,
    skip: uuid.UUID | None = None,
) -> int:
    """One feed entry (and push) per person, never to `skip` (the person who caused the event)."""
    ids = [i for i in dict.fromkeys(user_ids) if i != skip]
    for uid in ids:
        db.add(StaffNotification(user_id=uid, kind=kind, title=title[:160], body=body[:500], ref_id=str(ref_id) if ref_id else None))
    if ids and external_notify.push_configured():
        tokens = list(db.execute(select(StaffDevice.token).where(StaffDevice.user_id.in_(ids))).scalars())
        external_notify._push(tokens, title, body, {"kind": kind, "ref_id": str(ref_id or ""), "audience": "staff"})
    return len(ids)
