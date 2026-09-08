"""
Organization = the tenant boundary. VEEKAY (internal) and each partner
(BLINKIT, ZEPTO, ...) are all rows here, not special-cased in code.
Every user, and eventually every store/order/ticket, is scoped to one.
"""
from enum import StrEnum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationKind(StrEnum):
    INTERNAL = "internal"   # Veekay itself
    PARTNER = "partner"     # Blinkit, Zepto, future partners


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # "veekay", "blinkit", "zepto"
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default=OrganizationKind.PARTNER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
