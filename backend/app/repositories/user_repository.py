"""
Data-access layer for users. Routes and services never issue raw
queries against User/Role/Permission — they go through here, so the
query shape (joins, indexes used) can change in one place.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.permission import Permission, RolePermission
from app.models.role import Role
from app.models.user import User, UserRole
from app.models.user_permission import UserPermission


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_org_and_code(self, organization_id: uuid.UUID, employee_code: str) -> User | None:
        stmt = select(User).where(
            User.organization_id == organization_id,
            func.lower(User.employee_code) == employee_code.strip().lower(),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def code_exists(self, organization_id: uuid.UUID, employee_code: str) -> bool:
        return self.get_by_org_and_code(organization_id, employee_code) is not None

    def get_permission_codes(self, user_id: uuid.UUID) -> set[str]:
        """Union of role-granted permissions and direct per-user grants."""
        from_roles = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        direct = (
            select(Permission.code)
            .join(UserPermission, UserPermission.permission_id == Permission.id)
            .where(UserPermission.user_id == user_id)
        )
        codes = set(self.db.execute(from_roles).scalars().all())
        codes.update(self.db.execute(direct).scalars().all())
        return codes

    def get_direct_permission_codes(self, user_id: uuid.UUID) -> set[str]:
        stmt = (
            select(Permission.code)
            .join(UserPermission, UserPermission.permission_id == Permission.id)
            .where(UserPermission.user_id == user_id)
        )
        return set(self.db.execute(stmt).scalars().all())

    def get_role_codes(self, user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def set_direct_permissions(self, user_id: uuid.UUID, codes: list[str]) -> None:
        wanted = set(codes)
        perm_rows = self.db.execute(
            select(Permission.id, Permission.code).where(Permission.code.in_(wanted))
        ).all()
        found = {code: pid for pid, code in perm_rows}
        missing = wanted - set(found)
        if missing:
            from fastapi import HTTPException, status

            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unknown permission code(s): {', '.join(sorted(missing))}",
            )
        self.db.execute(UserPermission.__table__.delete().where(UserPermission.user_id == user_id))
        for pid in found.values():
            self.db.add(UserPermission(user_id=user_id, permission_id=pid))
        self.db.flush()

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
