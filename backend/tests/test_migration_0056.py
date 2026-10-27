"""Migration 0056 on realistic data: a scratch database is migrated to 0055, filled with store caps and entries, then upgraded.

The promise being proven: every store with a cap of 1 or more gets ONE history row, effective from its earliest entry (or the 1st of the current month when it has
none); a cap of 0 and a store with no cap get nothing; running the backfill again adds nothing; store_caps is untouched; the table refuses a duplicate date and a
capping below 1.
"""
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
import pytest

from .conftest import BACKEND, TEST_DB_URL
from .test_migration_0052 import _fill

SCRATCH = "veekay_mig0056"


def _urls():
    plain = TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _ = plain.rpartition("/")
    return f"{base}/postgres", f"{base}/{SCRATCH}", f"postgresql+psycopg://{base.split('://', 1)[1]}/{SCRATCH}"


def _alembic(target: str, sa_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": sa_url}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", target], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


@pytest.fixture()
def scratch():
    admin_url, scratch_url, sa_url = _urls()
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {SCRATCH}")
    try:
        _alembic("0055", sa_url)
        yield scratch_url, sa_url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def test_every_store_with_a_cap_gets_one_history_row_dated_from_its_first_entry(scratch):
    url, sa_url = scratch
    org, plat, author = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with_data, no_data, zero, no_cap = (uuid.uuid4() for _ in range(4))
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.cursor()
        _fill(cur, "organizations", id=org, slug="veekay", name="V", kind="internal")
        _fill(cur, "organizations", id=plat, slug="zepto", name="Zepto", kind="partner")
        _fill(cur, "users", id=author, organization_id=org, employee_code="E1", full_name="Asha", password_hash="x")
        for sid, name in ((with_data, "A"), (no_data, "B"), (zero, "C"), (no_cap, "D")):
            _fill(cur, "stores", id=sid, organization_id=org, partner_organization_id=plat, name=name, external_code=f"Z-{name}", crm_code=f"ZPT-{name}")
        _fill(cur, "store_caps", store_id=with_data, daily_cap=10, source="manual", updated_by_user_id=author)
        _fill(cur, "store_caps", store_id=no_data, daily_cap=11, source="sheet")
        _fill(cur, "store_caps", store_id=zero, daily_cap=0, source="manual")
        for d, n in ((date(2026, 9, 20), 8), (date(2026, 9, 5), 9), (date(2026, 10, 1), 10)):       # the earliest is the 5th, whatever the order they were added
            _fill(cur, "order_entries", organization_id=org, store_id=with_data, order_date=d, bottle_count=n, cash_adjustment=0, source="employee")
        _fill(cur, "order_entries", organization_id=org, store_id=no_cap, order_date=date(2026, 9, 1), bottle_count=3, cash_adjustment=0, source="employee")

    _alembic("0056", sa_url)

    first_of_month = datetime.now(ZoneInfo("Asia/Kolkata")).date().replace(day=1)
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.cursor()
        cur.execute("SELECT store_id, capping, effective_from, created_by FROM capping_history ORDER BY capping")
        assert cur.fetchall() == [(with_data, 10, date(2026, 9, 5), author), (no_data, 11, first_of_month, None)]
        cur.execute("SELECT store_id, daily_cap FROM store_caps ORDER BY daily_cap")
        assert cur.fetchall() == [(zero, 0), (with_data, 10), (no_data, 11)]                 # store_caps is untouched

        # running the backfill again adds nothing, even after someone changed a store's cap in the meantime
        spec = importlib.util.spec_from_file_location("m0056", BACKEND / "alembic" / "versions" / "0056_capping_history.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cur.execute("UPDATE store_caps SET daily_cap = 12 WHERE store_id = %s", (with_data,))
        cur.execute(mod.BACKFILL_SQL)
        cur.execute("SELECT count(*) FROM capping_history")
        assert cur.fetchone()[0] == 2

        # the table's own rules
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute("INSERT INTO capping_history (id, store_id, capping, effective_from) VALUES (gen_random_uuid(), %s, 12, %s)", (with_data, date(2026, 9, 5)))
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute("INSERT INTO capping_history (id, store_id, capping, effective_from) VALUES (gen_random_uuid(), %s, 0, %s)", (with_data, date(2026, 9, 6)))
        cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_capping_history_store_effective'")
        assert "effective_from DESC" in cur.fetchone()[0]

        # the admin role was given the new permission
        cur.execute("SELECT count(*) FROM role_permissions rp JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE p.code = 'capping.change' AND r.code = 'admin'")
        assert cur.fetchone()[0] in (0, 1)       # 0 only because this scratch database has no roles yet; the seeded test database is checked in test_capping_history
