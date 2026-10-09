"""
Data access for employees — users in one organization who hold the
'employee' role. Admin users are excluded from these lists.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.role import Role
from app.models.state_assignment import StateAssignment
from app.models.user import User, UserRole

EMPLOYEE_ROLE_CODE = "employee"


class EmployeeRepository:
    def __init__(self, db: Session):
        self.db = db

    def _employee_ids_subquery(self):
        return (
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code == EMPLOYEE_ROLE_CODE)
            .scalar_subquery()
        )

    def _role_ids_subquery(self, *codes: str):
        return select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code.in_(codes)).scalar_subquery()

    def get(self, org_id: uuid.UUID, user_id: uuid.UUID, *, include_admins: bool = False) -> User | None:
        stmt = (
            select(User)
            .where(
                User.organization_id == org_id,
                User.id == user_id,
                User.id.in_(self._role_ids_subquery(EMPLOYEE_ROLE_CODE, "accountant", "partner", "manager", "admin")),
                *([] if include_admins else [User.id.not_in(self._role_ids_subquery("admin"))]),
            )
            .options(joinedload(User.region), joinedload(User.platform_organization))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def all_for_platform(self, org_id: uuid.UUID, partner_id: uuid.UUID) -> list[User]:
        stmt = (
            select(User)
            .where(
                User.organization_id == org_id,
                User.platform_organization_id == partner_id,
                User.is_active.is_(True),
                User.id.in_(self._employee_ids_subquery()),
            )
            .options(joinedload(User.region))
            .order_by(User.full_name)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list(
        self,
        org_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        q: str | None = None,
        region_id: uuid.UUID | None = None,
        platform_id: uuid.UUID | None = None,
        category: str | None = None,
    ) -> tuple[list[User], int]:
        # The Team page shows all staff — admins, accounts and field employees — split by category.
        base = (
            select(User)
            .where(
                User.organization_id == org_id,
                User.id.in_(self._role_ids_subquery(EMPLOYEE_ROLE_CODE, "accountant", "partner", "manager", "admin")),
            )
            .options(joinedload(User.region), joinedload(User.platform_organization))
        )
        admin_ids = self._role_ids_subquery("admin", "manager")  # full admins and custom admins
        accountant_ids = self._role_ids_subquery("accountant")
        if category == "admin":
            base = base.where(User.id.in_(admin_ids))
        elif category == "accounts":
            base = base.where(User.id.in_(accountant_ids), User.id.not_in(admin_ids))
        elif category == "partner":
            base = base.where(User.id.in_(self._role_ids_subquery("partner")), User.id.not_in(admin_ids))
        elif category in ("blinkit", "zepto"):
            from app.models.organization import Organization

            base = base.join(Organization, Organization.id == User.platform_organization_id).where(
                func.lower(Organization.slug) == category, User.id.not_in(admin_ids), User.id.not_in(accountant_ids),
                User.id.not_in(self._role_ids_subquery("partner")),
            )
        if q:
            like = f"%{q.lower()}%"
            base = base.where(
                or_(
                    func.lower(User.full_name).like(like),
                    func.lower(User.email).like(like),
                    func.lower(User.employee_code).like(like),
                )
            )
        if region_id is not None:
            from app.models.employee_scope import EmployeeRegion

            base = base.where(or_(User.region_id == region_id, User.id.in_(select(EmployeeRegion.user_id).where(EmployeeRegion.region_id == region_id))))
        if platform_id is not None:
            base = base.where(User.platform_organization_id == platform_id)

        total = self.db.execute(
            select(func.count()).select_from(base.with_only_columns(User.id).order_by(None).subquery())
        ).scalar_one()
        rows = (
            self.db.execute(base.order_by(User.full_name).offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )
        return list(rows), total

    def active_full_admin_count(self, org_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(User).where(
            User.organization_id == org_id, User.is_active.is_(True), User.id.in_(self._role_ids_subquery("admin"))
        )
        return int(self.db.execute(stmt).scalar_one())

    def role_codes(self, user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def states_for(self, user_id: uuid.UUID) -> list[str]:
        stmt = select(StateAssignment.state).where(StateAssignment.assigned_user_id == user_id).order_by(StateAssignment.state)
        return list(self.db.execute(stmt).scalars().all())

    def email_exists(self, org_id: uuid.UUID, email: str) -> bool:
        stmt = select(User.id).where(
            User.organization_id == org_id, func.lower(User.email) == email.lower()
        )
        return self.db.execute(stmt).first() is not None
