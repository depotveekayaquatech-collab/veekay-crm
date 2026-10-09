"""
Extra scope for a region-model employee (Blinkit):

  EmployeeRegion    — every region the employee covers (so one person can cover several). `users.region_id` stays as the
                      first / main one, so everything that only knows one region keeps working.
  EmployeeExclusion — a specific state or city, with a mode:
                        skip : taken OUT of what the employee sees ("all of North, except Delhi")
                        add  : given IN ADDITION to their regions, or on its own ("North, plus Pune")
                      Skipping always wins over adding.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmployeeRegion(Base):
    __tablename__ = "employee_regions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    region_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True, index=True)


class ExclusionKind:
    STATE = "state"
    CITY = "city"


class ScopeMode:
    SKIP = "skip"
    ADD = "add"


class EmployeeExclusion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employee_exclusions"
    __table_args__ = (
        UniqueConstraint("user_id", "mode", "kind", "value", name="uq_employee_exclusion"),
        CheckConstraint("mode IN ('skip','add')", name="ck_employee_exclusion_mode"),
        CheckConstraint("kind IN ('state','city')", name="ck_employee_exclusion_kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(8), default="skip", server_default="skip")
    value: Mapped[str] = mapped_column(String(128))      # lower-cased, trimmed: what stores are matched against
    label: Mapped[str] = mapped_column(String(128))      # as shown to people
