"""
CappingHistory = one change of a store's DAILY capping, effective from a date.

The capping of a store on day D is the capping of the row with the greatest effective_from <= D (10 from the 1st and 11 from the 15th
give 10 on days 1-14 and 11 from day 15). Append-only as far as the API goes: there is no endpoint that edits or deletes a row. The
`store_caps` row stays the "current capping" (the capping effective today) so everything that already reads it keeps working.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class CappingHistory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "capping_history"
    __table_args__ = (
        UniqueConstraint("store_id", "effective_from", name="uq_capping_history_store_date"),
        CheckConstraint("capping IS NULL OR capping >= 1", name="ck_capping_history_capping"),
        Index("ix_capping_history_store_effective", "store_id", text("effective_from DESC")),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"))
    # Bottles per day from effective_from; NULL = the capping was REMOVED from that date (the days before keep theirs).
    capping: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    # Null only when the person's account was deleted later, or for a backfilled row whose cap had no known author.
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
