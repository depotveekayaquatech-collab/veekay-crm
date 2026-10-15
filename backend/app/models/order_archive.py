"""
OrderEntryArchive = a safety copy of order history taken when stores are wiped (developer "Remove all stores").

Stores are identified by (partner, external_code), not by id, because the store row is about to disappear.
When a store with the same partner + code is created or imported again, its archived days are put back into
order_entries automatically (see store_service.restore_archived_history), so history is never lost to a re-import.
"""
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrderEntryArchive(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "order_entry_archive"
    __table_args__ = (
        UniqueConstraint("partner_organization_id", "external_code", "order_date", name="uq_order_archive_store_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    partner_organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    external_code: Mapped[str] = mapped_column(String(64), index=True)
    store_name: Mapped[str] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_date: Mapped[date] = mapped_column(Date)
    bottle_count: Mapped[int] = mapped_column(Integer)
    cash_adjustment: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(32), default="stores_wiped")
