"""
Attendance, derived from sign-in / sign-out.

Office            = a place that counts as "at the office" (a point and a radius).
AttendanceSession = one sign-in (one session family) with its login / logout time and
                    where the person was when they signed in.

A day's attendance is a summary of that day's sessions: first sign-in, last explicit
sign-out, and active minutes (overlapping sessions on several devices are merged).
A session the person never signed out of ends at the last time we saw it active.

Location is captured by the browser at sign-in and classified here, on the server,
against the active offices: within an office's radius -> that office's name, otherwise
the exact coordinates are kept. The coordinates come from the device, so they can be
spoofed; treat them as evidence, not proof.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Office(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "offices"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AttendanceSession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "attendance_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    work_date: Mapped[date] = mapped_column(Date, index=True)          # local date of the sign-in
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)  # = the auth session family

    login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    logout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[str | None] = mapped_column(String(10), nullable=True)  # logout | revoked (None = open / idle)

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # where they signed in
    location_status: Mapped[str] = mapped_column(String(10), default="unknown")  # office | outside | unknown
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)   # to the nearest active office
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offices.id", ondelete="SET NULL"), nullable=True
    )
    location_label: Mapped[str | None] = mapped_column(String(128), nullable=True)  # office name when inside
