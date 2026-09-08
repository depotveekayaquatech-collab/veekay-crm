"""
Roles group permissions for convenience (assigning "Regional Manager"
beats assigning 12 permissions by hand) but are never checked by name
in business logic — only the permissions attached to them are.
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"

    # e.g. "super_admin", "admin", "regional_manager", "employee", "blinkit_admin", "zepto_admin"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
