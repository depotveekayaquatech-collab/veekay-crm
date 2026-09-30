"""
User = an authenticated person. Always scoped to exactly one
organization. Field employees log in with an Employee ID
(`employee_code`) + password; every actual permission is the union of
their roles' permissions and any direct grants (see UserPermission).
"""
import uuid
from enum import StrEnum

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus(StrEnum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    LOCKED = "locked"  # temporary, from failed-login protection


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_code", name="uq_org_employee_code"),
        UniqueConstraint("organization_id", "email", name="uq_org_email"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    # The partner platform (Blinkit / Zepto) a field employee serves. Null for
    # admins and internal staff.
    platform_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # Blinkit employees are scoped to one region; Zepto employees are scoped by
    # state (see StateAssignment) and leave this null.
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    employee_code: Mapped[str] = mapped_column(String(32), index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    password_hash: Mapped[str] = mapped_column(String(255))
    # True for admin-set / generated / imported passwords: the person must choose their own before doing anything else.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE.value)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO timestamp, set on lockout

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # soft-delete / deactivation flag

    organization: Mapped["Organization"] = relationship(
        back_populates="users", foreign_keys=[organization_id]
    )
    platform_organization: Mapped["Organization | None"] = relationship(
        foreign_keys=[platform_organization_id]
    )
    region: Mapped["Region | None"] = relationship()
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    permission_grants: Mapped[list["UserPermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserRole(Base, TimestampMixin):
    """Many-to-many: a user can hold more than one role (rare but the
    model should not forbid e.g. Regional Manager + Blinkit Admin)."""
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship()
