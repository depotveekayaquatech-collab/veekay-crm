"""
Bottle QR tracking.

Every physical bottle carries one QR code whose text is a unique, random serial (VK-XXXX-XXXX). A serial is the
bottle's identity: it is scanned IN when the bottle reaches a store and OUT when it leaves. A bottle that was scanned
IN and never OUT is "at the store"; once that is older than BOTTLE_LOST_AFTER_DAYS it is overdue (possibly lost).
A code that was printed but never scanned (UNUSED) is simply stock — it is never reported as missing.

When a QR is damaged, a NEW serial replaces it (`replaces_id` / `replaced_by_id`): the old one is RETIRED and the new
one inherits where the bottle is. Scans are append-only, so history is never rewritten.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BottleStatus:
    UNUSED = "UNUSED"        # printed, never scanned
    AT_STORE = "AT_STORE"    # last scan was IN
    RETURNED = "RETURNED"    # last scan was OUT
    RETIRED = "RETIRED"      # QR replaced / bottle written off; scans are refused
    DELETED = "DELETED"      # deleted by the developer: never scannable again, but the record and its history are kept


class ScanDirection:
    IN = "IN"
    OUT = "OUT"


class BottleBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bottle_batches"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255))


class Bottle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bottles"
    __table_args__ = (
        Index("ix_bottles_batch_seq", "batch_id", "seq"),
        Index("ix_bottles_status_last_in", "organization_id", "status", "last_in_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    serial: Mapped[str] = mapped_column(String(16), unique=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bottle_batches.id", ondelete="SET NULL"), nullable=True)
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)   # position inside the batch (print order)

    status: Mapped[str] = mapped_column(String(16), default=BottleStatus.UNUSED, server_default=BottleStatus.UNUSED)
    current_store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True)
    last_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replaces_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bottles.id", ondelete="SET NULL"), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bottles.id", ondelete="SET NULL"), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retire_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BottleScan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only. `warning` is set when the scan did not follow the normal IN -> OUT order."""
    __tablename__ = "bottle_scans"
    __table_args__ = (
        Index("ix_bottle_scans_bottle_time", "bottle_id", "scanned_at"),
        CheckConstraint("direction IN ('IN','OUT')", name="ck_bottle_scan_direction"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    bottle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bottles.id", ondelete="CASCADE"))
    serial: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(3))
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)   # snapshot, survives store edits
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(16))                              # "app" | "api"
    scanned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scanned_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_scan_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)  # makes retries / offline re-sends safe
    warning: Mapped[str | None] = mapped_column(String(255), nullable=True)
