"""check in / check out attendance, leave requests

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_in_status", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("check_in_lat", sa.Float(), nullable=True),
        sa.Column("check_in_lng", sa.Float(), nullable=True),
        sa.Column("check_in_accuracy_m", sa.Float(), nullable=True),
        sa.Column("check_in_distance_m", sa.Float(), nullable=True),
        sa.Column("check_in_label", sa.String(128), nullable=True),
        sa.Column("late", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_status", sa.String(10), nullable=True),
        sa.Column("check_out_lat", sa.Float(), nullable=True),
        sa.Column("check_out_lng", sa.Float(), nullable=True),
        sa.Column("check_out_accuracy_m", sa.Float(), nullable=True),
        sa.Column("check_out_distance_m", sa.Float(), nullable=True),
        sa.Column("check_out_label", sa.String(128), nullable=True),
        sa.Column("source", sa.String(10), nullable=False, server_default="checkin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "work_date", name="uq_attendance_user_date"),
    )
    op.create_index("ix_attendance_records_organization_id", "attendance_records", ["organization_id"])
    op.create_index("ix_attendance_records_user_id", "attendance_records", ["user_id"])
    op.create_index("ix_attendance_records_work_date", "attendance_records", ["work_date"])

    op.create_table(
        "leave_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("leave_type", sa.String(10), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("half_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("days", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leave_requests_organization_id", "leave_requests", ["organization_id"])
    op.create_index("ix_leave_requests_user_id", "leave_requests", ["user_id"])
    op.create_index("ix_leave_requests_start_date", "leave_requests", ["start_date"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])

    bind = op.get_bind()

    # Carry earlier (login-based) attendance over: first sign-in of the day = check in, last explicit sign-out = check out.
    bind.execute(sa.text("""
        INSERT INTO attendance_records (
            id, organization_id, user_id, work_date, check_in_at, check_in_status, check_in_lat, check_in_lng,
            check_in_accuracy_m, check_in_distance_m, check_in_label, late, check_out_at, source, created_at, updated_at
        )
        SELECT gen_random_uuid(), f.organization_id, f.user_id, f.work_date, f.login_at, f.location_status, f.latitude,
               f.longitude, f.accuracy_m, f.distance_m, f.location_label, false, o.last_out, 'legacy', now(), now()
        FROM (
            SELECT DISTINCT ON (user_id, work_date) *
            FROM attendance_sessions ORDER BY user_id, work_date, login_at
        ) f
        LEFT JOIN (
            SELECT user_id, work_date, max(logout_at) AS last_out
            FROM attendance_sessions WHERE ended_by = 'logout' GROUP BY user_id, work_date
        ) o ON o.user_id = f.user_id AND o.work_date = f.work_date
    """))

    perm_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'leave.review'")).scalar()
    if perm_id is None:
        perm_id = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'leave.review', :d)"),
            {"i": perm_id, "d": "Approve or reject leave requests"},
        )
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) "
                "VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"
            ),
            {"r": role_id, "p": perm_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM permissions WHERE code = 'leave.review'"))
    op.drop_table("leave_requests")
    op.drop_table("attendance_records")
