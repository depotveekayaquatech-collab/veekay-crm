"""
Ticket = a problem raised against one store (late delivery, short supply, quality ...).

A ticket belongs to a store, so it is automatically routed by that store's region (Blinkit) or state (Zepto): the
field employees who handle the store see it, and admins see every region. Partner accounts (Blinkit / Zepto logins)
see and raise tickets for their own platform only.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TicketCategory(StrEnum):
    LATE_DELIVERY = "LATE_DELIVERY"
    NO_DELIVERY = "NO_DELIVERY"
    SHORT_SUPPLY = "SHORT_SUPPLY"
    QUALITY = "QUALITY"
    DAMAGED = "DAMAGED"
    BILLING = "BILLING"
    OTHER = "OTHER"


ACTIVE_STATUSES = (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
# Categories that count as a delivery failure on the admin insights.
DELIVERY_CATEGORIES = (TicketCategory.LATE_DELIVERY.value, TicketCategory.NO_DELIVERY.value)
# Hours a ticket may stay unresolved before it is flagged overdue.
SLA_HOURS = {"URGENT": 12, "HIGH": 24, "MEDIUM": 48, "LOW": 96}


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tickets"

    number: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True
    )
    partner_organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )

    category: Mapped[str] = mapped_column(String(24), index=True)
    priority: Mapped[str] = mapped_column(String(10), default=TicketPriority.MEDIUM.value)
    status: Mapped[str] = mapped_column(String(12), default=TicketStatus.OPEN.value, index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Tickets pushed in from outside (Google Apps Script): `external_id` makes a retry harmless, `reporter` says who raised it.
    source: Mapped[str] = mapped_column(String(16), default="app")   # app | google
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    store: Mapped["Store"] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_user_id])
    comments: Mapped[list["TicketComment"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketComment.created_at"
    )


class TicketComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text)
    # A status change recorded as a line in the thread ("Status: OPEN → IN_PROGRESS"); empty for normal comments.
    event: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship()
