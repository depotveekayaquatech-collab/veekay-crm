"""
Region = a flat operational area Veekay runs (e.g. "Delhi NCR", "Mumbai").
No hierarchy. Always scoped to the Veekay organization — partners don't
own regions. Employees belong to one region; stores sit in one region.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Region(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "regions"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_region_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )

    name: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship()
    stores: Mapped[list["Store"]] = relationship(back_populates="region")
