"""
VendorRate = what Veekay (the vendor) charges per bottle, by city, for one platform; optionally a rate for a single store
that overrides its city's rate. Rates are effective-dated: a new upload adds rows from its effective date and the old rows
stay as history, so the rate for any date can be looked up.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VendorRate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "vendor_rates"
    __table_args__ = (Index("ix_vendor_rates_lookup", "partner_organization_id", "city_key", "store_id", "effective_from"),)

    partner_organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    city_key: Mapped[str] = mapped_column(String(64))                    # lower-cased city, the lookup key
    city: Mapped[str] = mapped_column(String(64))                         # as written in the sheet
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), nullable=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))                 # per bottle
    effective_from: Mapped[date] = mapped_column(Date)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
