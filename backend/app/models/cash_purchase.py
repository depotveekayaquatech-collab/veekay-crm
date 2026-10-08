"""
CashPurchase = one small cash payment made on the company's behalf: either for the office (stationery, milk, water
bottles ...) or for a specific store (a repair, a part, local transport ...).

`category` is a code from the lists below; `OTHER` requires a free-text `other_reason`. Rows are never edited or
removed through the app, so the sheet always matches what was entered; mistakes are handled by an admin in the DB.
"""
import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PurchaseKind(StrEnum):
    OFFICE = "OFFICE"
    STORE = "STORE"


OTHER = "OTHER"

# code -> label, in dropdown order. "Other" is always last and asks for a description.
OFFICE_REASONS: dict[str, str] = {
    "MILK": "Milk",
    "STATIONERY": "Stationery",
    "TOILETRIES": "Toiletries & hygiene supplies",
    "CLEANING": "Cleaning supplies",
    "PANTRY": "Pantry supplies (tea, coffee, sugar)",
    "DRINKING_WATER": "Drinking water",
    OTHER: "Other",
}
# A store purchase is always water bottles; its `category` records WHY it had to be bought in cash.
STORE_ITEM = "Water bottles"
STORE_REASONS: dict[str, str] = {
    "VENDOR_NOT_RESPONDING": "Vendor not responding",
    "SUPPLY_DELAYED": "Supply delayed",
    "EMERGENCY_REQUIREMENT": "Emergency water requirement",
    "NEW_STORE_URGENT": "New store (urgent requirement)",
    OTHER: "Other",
}
REASONS_BY_KIND = {PurchaseKind.OFFICE.value: OFFICE_REASONS, PurchaseKind.STORE.value: STORE_REASONS}


class CashPurchase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cash_purchases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purchase_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(32))
    other_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    proof_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proof_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    store = relationship("Store", lazy="joined")
    created_by = relationship("User", lazy="joined", foreign_keys=[created_by_user_id])
