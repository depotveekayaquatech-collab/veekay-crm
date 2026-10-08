"""
CashAdjustment = the developer-only history of cash-purchase adjustments to the order sheet.

One row per store per applied operation (a multi-store operation shares a batch_id). Rows are append-only: they
carry a snapshot of the outlet code / name and the developer's name, so the history still reads correctly if the
store or the user changes later. Never exposed to anyone without the reserved `cash.adjust` permission.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CashAdjustment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cash_adjustments"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True)
    outlet_code: Mapped[str] = mapped_column(String(64))
    outlet_name: Mapped[str] = mapped_column(String(255))
    purchase_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_per_item: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    auto_qty: Mapped[int] = mapped_column(Integer)
    final_qty: Mapped[int] = mapped_column(Integer)
    previous_qty: Mapped[int] = mapped_column(Integer)
    final_order_qty: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255))
    sync_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="Manual", server_default="Manual")
    action: Mapped[str] = mapped_column(String(32), default="Applied", server_default="Applied")


class CashSyncRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One click of "Sync Cash Purchase": what it found. Developer-only."""
    __tablename__ = "cash_sync_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255))
    records_found: Mapped[int] = mapped_column(Integer)
    new_count: Mapped[int] = mapped_column(Integer)
    changed_count: Mapped[int] = mapped_column(Integer)
    already_count: Mapped[int] = mapped_column(Integer)


class SyncStatus:
    PENDING = "PENDING"    # new: waiting for the developer's review
    CHANGED = "CHANGED"    # the source purchase changed after the last sync: needs a decision
    APPLIED = "APPLIED"    # added to the order sheet (never added again)
    SKIPPED = "SKIPPED"    # the developer chose not to apply it


class CashSyncRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    The developer's working copy of one store purchase. store / date / amount / price are editable until it is
    applied; `baseline` is the source as it was when synced or last accepted, `current_source` the latest source.
    One row per source purchase (unique purchase_id), so syncing again can never create a second one.
    """
    __tablename__ = "cash_sync_records"
    __table_args__ = (UniqueConstraint("organization_id", "purchase_id", name="uq_cash_sync_record_purchase"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    purchase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True)
    purchase_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_per_item: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_qty_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline: Mapped[dict] = mapped_column(JSONB)
    current_source: Mapped[dict] = mapped_column(JSONB)
    sync_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    applied_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
