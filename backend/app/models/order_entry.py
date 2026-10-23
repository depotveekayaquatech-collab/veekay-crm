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
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # The part of bottle_count added by developer cash-purchase adjustments. bottle_count is always the FINAL number
    # (what every report shows); the employee's real entry is bottle_count - cash_adjustment. Never shown to employees.
    cash_adjustment: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(String(16), default=EntrySource.EMPLOYEE.value)

    marked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ---- ownership + audit (migration 0052). All of these are stamped by database triggers from the authenticated request: nothing the client
    # sends can set them, and the creator can never be changed. `marked_by_user_id` above is only "the last person who set the number".
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)   # no FK on purpose: identity outlives the account
    created_by_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")   # False = legacy / written with no known actor
    created_via: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_modified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_modified_by_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(String(24), default="none", server_default="none")
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)       # the client's idempotency key for this entry
    source_app: Mapped[str | None] = mapped_column(Text, nullable=True)

    store: Mapped["Store"] = relationship()
    marked_by: Mapped["User | None"] = relationship()
