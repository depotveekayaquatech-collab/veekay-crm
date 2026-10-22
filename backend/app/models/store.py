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

from sqlalchemy import Date, ForeignKey, Index, String, event, text
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
        # The Outlet ID is not unique: a store's NAME is its identity. Repeats are listed under Stores > Duplicates.
        Index("ix_stores_partner_code", "partner_organization_id", "external_code"),
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
    # The store's permanent system code, e.g. BKT000123 (Blinkit) or ZPT000045 (Zepto): unique across the whole system, handed out
    # automatically, never edited. The Outlet ID and the name can repeat or change meaning between platforms; this never does.
    crm_code: Mapped[str] = mapped_column(String(16), unique=True)
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


# ---- system codes -------------------------------------------------------------------------------------------------------------
_PREFIXES = {"blinkit": "BKT", "zepto": "ZPT"}


def code_prefix(slug: str | None) -> str:
    """BKT for Blinkit, ZPT for Zepto; any other platform gets the first three letters of its name."""
    slug = (slug or "").strip().lower()
    if slug in _PREFIXES:
        return _PREFIXES[slug]
    letters = "".join(ch for ch in slug if ch.isalnum()).upper()
    return (letters[:3] or "STR").ljust(3, "X")


def issue_crm_code(connection, partner_id) -> str:
    """The next unused code for a platform. The counter row is updated in the same transaction, so two stores never get one code."""
    slug = connection.execute(text("SELECT slug FROM organizations WHERE id = :i"), {"i": partner_id}).scalar()
    prefix = code_prefix(slug)
    n = connection.execute(
        text(
            "INSERT INTO store_code_counters (prefix, last_value) VALUES (:p, 1) "
            "ON CONFLICT (prefix) DO UPDATE SET last_value = store_code_counters.last_value + 1 RETURNING last_value"
        ),
        {"p": prefix},
    ).scalar_one()
    return f"{prefix}{n:06d}"


@event.listens_for(Store, "before_insert")
def _give_new_store_a_code(mapper, connection, target):          # every way of creating a store (forms, imports, scripts, tests) gets one
    if not target.crm_code:
        target.crm_code = issue_crm_code(connection, target.partner_organization_id)
