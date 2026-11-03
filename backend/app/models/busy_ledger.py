"""
Vendor payments fed from Busy 21 (the accounting software). The CRM only ever READS this data back out; it never logs in to Busy.

`vendor_code` is the one and only link between a Busy account and a CRM vendor (never the name). It is unique, never changes after the
vendor is created (a database trigger refuses it), and is what the sender's account name ends with, e.g. "Sharma Traders Gurugram V0123".

Named `busy_*` on purpose: "vendor" elsewhere in this system means Veekay's delivery side (vendor rates, the vendor portal), not these suppliers.

Money is NUMERIC(14,2), never a float. A ledger amount is always positive; `entry_type` says whether it is a BILL (we owe more) or a PAYMENT (we paid).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

BILL, PAYMENT = "BILL", "PAYMENT"
ENTRY_TYPES = (BILL, PAYMENT)
SOURCE_API, SOURCE_CSV, SOURCE_MANUAL = "API", "CSV", "MANUAL"
SOURCES = (SOURCE_API, SOURCE_CSV, SOURCE_MANUAL)
STATUS_SUCCESS, STATUS_PARTIAL, STATUS_FAILED = "SUCCESS", "PARTIAL", "FAILED"
UNMATCHED_OPEN, UNMATCHED_RESOLVED = "OPEN", "RESOLVED"


class BusyVendor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "busy_vendors"

    vendor_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))   # owed to the vendor as of opening_date
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)                    # always the 1st of a month
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BusyVendorAlias(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Another code that Busy uses for an existing vendor (set by an admin from the unmatched list). Still matching by code, never by name."""

    __tablename__ = "busy_vendor_aliases"

    alias_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    vendor_code: Mapped[str] = mapped_column(String(32), ForeignKey("busy_vendors.vendor_code", ondelete="RESTRICT"), index=True)


class BusyLedgerEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "busy_ledger_entries"
    __table_args__ = (
        UniqueConstraint("vendor_code", "voucher_no", "entry_type", name="uq_busy_ledger_key"),
        CheckConstraint("amount > 0", name="ck_busy_ledger_amount_positive"),
        CheckConstraint("entry_type IN ('BILL','PAYMENT')", name="ck_busy_ledger_type"),
        CheckConstraint("source IN ('API','CSV','MANUAL')", name="ck_busy_ledger_source"),
        Index("ix_busy_ledger_vendor_date", "vendor_code", "entry_date"),
    )

    vendor_code: Mapped[str] = mapped_column(String(32), ForeignKey("busy_vendors.vendor_code", ondelete="RESTRICT"))
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    entry_type: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    voucher_no: Mapped[str] = mapped_column(String(64))
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(8))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BusySyncLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per authenticated sync call (API or CSV import). A dry run writes nothing."""

    __tablename__ = "busy_sync_logs"

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(120), nullable=True)           # the caller's IP, or the admin's name for a CSV import
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    rows_deleted: Mapped[int] = mapped_column(Integer, default=0)
    rows_unmatched: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(8), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class BusyUnmatchedEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A valid row whose vendor_code is not a CRM vendor (or that had no code at all). Kept with the raw row for an admin to resolve, never dropped."""

    __tablename__ = "busy_unmatched_entries"
    __table_args__ = (Index("ix_busy_unmatched_status_code", "status", "vendor_code"),)

    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)       # so re-sending the same data never piles up copies
    vendor_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_name: Mapped[str] = mapped_column(String(300), default="")
    entry_date: Mapped[date] = mapped_column(Date)
    entry_type: Mapped[str] = mapped_column(String(8))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    voucher_no: Mapped[str] = mapped_column(String(64))
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(8))
    raw: Mapped[dict] = mapped_column(JSONB)
    sync_log_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("busy_sync_logs.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(8), default=UNMATCHED_OPEN)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_vendor_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
