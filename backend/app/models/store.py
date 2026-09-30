"""
Store = a partner (Blinkit / Zepto) outlet Veekay delivers water to.

`organization_id`         — the Veekay org that owns this record.
`partner_organization_id` — the partner (platform) the store belongs to.
`external_code`           — the partner's own outlet id (e.g. "BLK-4821").
`status`                  — LIVE / PENDING / CLOSE (only LIVE stores are
                            visible to employees and countable in reports).

Which employee services a store is not stored here — it is resolved from
the store's region (Blinkit) or state (Zepto); see assignment_service.
"""
import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreStatus(StrEnum):
    LIVE = "LIVE"
    PENDING = "PENDING"
    CLOSE = "CLOSE"


class Store(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("partner_organization_id", "external_code", name="uq_store_partner_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    partner_organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="RESTRICT"), index=True, nullable=True
    )

    name: Mapped[str] = mapped_column(String(128))
    external_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=StoreStatus.LIVE.value, index=True)

    state: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)  # company entity, e.g. BCPL
    # The day supply to this store began. Optional; days before it are never counted as pending.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    poc_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    poc_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    region: Mapped["Region | None"] = relationship(back_populates="stores")
    partner_organization: Mapped["Organization"] = relationship(
        foreign_keys=[partner_organization_id]
    )
