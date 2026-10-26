"""Zero Review: a person's decision about a store's run of zero-order days, for one week or one month.

ZeroReview     = the CURRENT state of one (store, period): pending (no row yet) -> reviewed (weekly) / verified | flagged (monthly).
ZeroReviewLog  = append-only: every change of that state, who made it, when, and why. Never updated or deleted by the application.

The daily order numbers are NOT copied here (they stay in order_entries); a row only records what a person decided about them.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ZeroReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "zero_review"
    __table_args__ = (UniqueConstraint("store_id", "period_type", "period_start", name="uq_zero_review_store_period"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    period_type: Mapped[str] = mapped_column(String(8))                       # week | month
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    threshold_used: Mapped[int | None] = mapped_column(Integer, nullable=True)  # the "N consecutive zeros" that flagged it
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(10))                           # pending | reviewed | verified | flagged
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class ZeroReviewLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "zero_review_log"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True)   # null: a month-level event
    period_type: Mapped[str] = mapped_column(String(8))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    event: Mapped[str] = mapped_column(String(24))                            # reviewed | verified | flagged | month_reopened | closed_month_verified
    from_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    threshold_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    longest_streak: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)      # no FK on purpose: the record outlives the account
    actor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
