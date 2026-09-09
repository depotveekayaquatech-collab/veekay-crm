"""
OrderEntry = one store's bottle count for one calendar date.

Invariants (see the functional spec):
  - Exactly one entry per (store, date). The DB unique constraint is the
    lock — an employee can submit a given store+date only once.
  - bottle_count 0..200. Zero is a real, "already marked" value — never
    conflated with "no entry" (no row at all = not marked).
  - source: 'employee' (one-shot, immutable by that employee) or 'admin'
    (a correction; admins may overwrite freely). Clearing = deleting the
    row, done by an admin only.

There is no physical monthly table — a month view is just the rows whose
order_date falls in that month.
"""
import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntrySource(StrEnum):
    EMPLOYEE = "employee"
    ADMIN = "admin"


class OrderEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "order_entries"
    __table_args__ = (UniqueConstraint("store_id", "order_date", name="uq_order_entry_store_date"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True
    )
    order_date: Mapped[date] = mapped_column(Date, index=True)
    bottle_count: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16), default=EntrySource.EMPLOYEE.value)

    marked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    store: Mapped["Store"] = relationship()
    marked_by: Mapped["User | None"] = relationship()
