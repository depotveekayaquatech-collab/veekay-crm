"""payroll: salaries, payout periods, day marks, payslips, and the payroll.manage permission

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-19
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "employee_salaries", *_base(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("monthly_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("monthly_salary >= 0", name="ck_employee_salaries_non_negative"),
    )
    op.create_table(
        "payroll_periods", *_base(),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Date, nullable=False),
        sa.Column("release_date", sa.Date, nullable=False),
        sa.Column("window_days", sa.Integer, nullable=False, server_default="3"),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("organization_id", "month", name="uq_payroll_period_month"),
    )
    op.create_index("ix_payroll_periods_organization_id", "payroll_periods", ["organization_id"])
    op.create_table(
        "payroll_day_marks", *_base(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("mark", sa.String(6), nullable=False),
        sa.Column("marked_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("user_id", "work_date", name="uq_payroll_day_mark"),
    )
    op.create_index("ix_payroll_day_marks_user_id", "payroll_day_marks", ["user_id"])
    op.create_table(
        "payslips", *_base(),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_id", UUID, sa.ForeignKey("payroll_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monthly_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("days_in_month", sa.Integer, nullable=False),
        sa.Column("paid_days", sa.Numeric(5, 1), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("breakdown", postgresql.JSONB, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("period_id", "user_id", name="uq_payslip_period_user"),
    )
    op.create_index("ix_payslips_organization_id", "payslips", ["organization_id"])
    op.create_index("ix_payslips_period_id", "payslips", ["period_id"])
    op.create_index("ix_payslips_user_id", "payslips", ["user_id"])

    bind = op.get_bind()
    pid = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'payroll.manage'")).scalar()
    if pid is None:
        pid = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:i, 'payroll.manage', :d)"),
            {"i": pid, "d": "Payroll: set salaries, review attendance for payslips, mark days and pay salaries"},
        )
    for (role_id,) in bind.execute(sa.text("SELECT id FROM roles WHERE code = 'admin'")).all():
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission_id, created_at, updated_at) VALUES (:r, :p, now(), now()) ON CONFLICT DO NOTHING"),
            {"r": role_id, "p": pid},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = 'payroll.manage'"))
    op.drop_table("payslips")
    op.drop_table("payroll_day_marks")
    op.drop_table("payroll_periods")
    op.drop_table("employee_salaries")
