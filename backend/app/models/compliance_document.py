"""
ComplianceDocument = one uploaded file for one store and one month.

kind 'card' — the store's compliance card.
kind 'bill' — the month's bill; carries a due date (month-end + 45 days) and a
              PENDING / CLEARED status that an accountant flips.

Exactly one row per (store, month, kind): re-uploading replaces the file in
place (the old file is deleted) and, for bills, keeps the cleared status.
`month` is always the first day of the month.
"""
import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocKind(StrEnum):
    CARD = "card"
    BILL = "bill"


class BillStatus(StrEnum):
    PENDING = "PENDING"
    CLEARED = "CLEARED"


class ComplianceDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "compliance_documents"
    __table_args__ = (UniqueConstraint("store_id", "month", "kind", name="uq_compliance_store_month_kind"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)

    file_key: Mapped[str] = mapped_column(String(512))       # path inside the storage root
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # bills only
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    store: Mapped["Store"] = relationship()
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_user_id])
