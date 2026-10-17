"""
StoreVendorPeriod = who supplied a store, and for which dates.

A store has at most ONE open period (end_date NULL): the current vendor, mirrored on Store.vendor_name/number so every
existing screen keeps working. When the vendor changes, that period is closed (end_date = the day before the new vendor
started) and a new one opens. `start_confirmed` is False until the new vendor's first order date has been seen in an
order sheet; until then the start is the day the change was noticed.
"""
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreVendorPeriod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "store_vendor_periods"
    __table_args__ = (
        Index("uq_store_vendor_one_open", "store_id", unique=True, postgresql_where=text("end_date IS NULL")),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(128))
    vendor_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)   # unknown for vendors that pre-date this feature
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)     # NULL = current vendor
    start_confirmed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    source: Mapped[str] = mapped_column(String(16), default="sheet")      # sheet | file | manual | backfill
    changed_by_name: Mapped[str | None] = mapped_column(String(128), nullable=True)   # who made the change (a name, so it survives user changes)
