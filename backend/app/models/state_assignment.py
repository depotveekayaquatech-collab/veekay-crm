"""
StateAssignment — for platforms with no region concept (Zepto), a state
is assigned to exactly one employee, who then sees every store in that
state. A state with no assignment is invisible to everyone until assigned.
"""
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StateAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "state_assignments"
    __table_args__ = (
        UniqueConstraint("partner_organization_id", "state", name="uq_state_assignment_partner_state"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    partner_organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    state: Mapped[str] = mapped_column(String(64), index=True)
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    assigned_user: Mapped["User"] = relationship()
