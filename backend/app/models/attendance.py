"""
Attendance.

Office            = a place that counts as "at the office" (a point and a radius).
AttendanceRecord  = one person's day: an explicit Check in and Check out, each with where they were.
LeaveRequest      = a leave application and its approval.
AttendanceSession = the old login-based sign-ins. No longer written; kept as history (carried into
                    AttendanceRecord by migration 0011).

Location is read by the browser when the person taps Check in / Check out and classified here, on the server,
against the active offices: within an office's radius -> that office's name, otherwise
the exact coordinates are kept. The coordinates come from the device, so they can be
spoofed; treat them as evidence, not proof.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
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


class AttendanceRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One person's attendance for one day: an explicit Check in and (later) Check out, each with its own location."""
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_attendance_user_date"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)  # local date of the check-in

    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_in_status: Mapped[str] = mapped_column(String(10), default="unknown")  # office | outside | unknown
    check_in_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)

    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    check_out_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_out_label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source: Mapped[str] = mapped_column(String(10), default="checkin")  # checkin | legacy (carried over from login sessions)


class LeaveRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A leave application: needs approval from someone holding `leave.review`."""
    __tablename__ = "leave_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    leave_type: Mapped[str] = mapped_column(String(10))   # CASUAL | SICK | PAID | UNPAID
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    days: Mapped[float] = mapped_column(Float)            # working days (Sundays excluded)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)  # PENDING | APPROVED | REJECTED | CANCELLED
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
