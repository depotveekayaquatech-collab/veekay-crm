"""
StoreCap = the DAILY bottle cap for one store (Zepto capping). The monthly limit is daily_cap x 30.

One row per store; no row means "no cap configured". 0 is a real cap (no bottles allowed), not "blank". The same cap
applies to every month until someone changes it. Set by an employee in the CRM, or loaded from the Capping sheet by a
developer (source "sheet"); every change is also written to the activity log.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoreCap(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "store_caps"

    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), unique=True)
    daily_cap: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(12), default="manual")   # manual | sheet | file
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
