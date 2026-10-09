"""specific states / cities can be ADDED to an employee's scope, not only skipped

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employee_exclusions", sa.Column("mode", sa.String(8), nullable=False, server_default="skip"))
    op.create_check_constraint("ck_employee_exclusion_mode", "employee_exclusions", "mode IN ('skip','add')")
    op.drop_constraint("uq_employee_exclusion", "employee_exclusions", type_="unique")
    op.create_unique_constraint("uq_employee_exclusion", "employee_exclusions", ["user_id", "mode", "kind", "value"])


def downgrade() -> None:
    op.execute("DELETE FROM employee_exclusions WHERE mode = 'add'")
    op.drop_constraint("uq_employee_exclusion", "employee_exclusions", type_="unique")
    op.create_unique_constraint("uq_employee_exclusion", "employee_exclusions", ["user_id", "kind", "value"])
    op.drop_constraint("ck_employee_exclusion_mode", "employee_exclusions", type_="check")
    op.drop_column("employee_exclusions", "mode")
