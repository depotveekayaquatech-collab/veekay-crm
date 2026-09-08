"""
Data-access layer for users. Routes and services never issue raw
queries against User/Role/Permission — they go through here, so the
query shape (joins, indexes used) can change in one place.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission, RolePermission
from app.models.role import Role
from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_org_and_email(self, organization_id: uuid.UUID, email: str) -> User | None:
        stmt = select(User).where(
            User.organization_id == organization_id, User.email == email.lower()
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_permission_codes(self, user_id: uuid.UUID) -> set[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        return set(self.db.execute(stmt).scalars().all())

    def get_role_codes(self, user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
