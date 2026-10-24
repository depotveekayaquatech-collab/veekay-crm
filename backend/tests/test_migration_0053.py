"""Migration 0053 on realistic data: a scratch database is migrated to 0052, filled with entries (some already marked `reviewed` by a reviewer), then upgraded.

The promise being proven: every existing entry starts as `submitted` (nobody has verified them), an entry a reviewer had marked `reviewed` becomes
`reviewed_l3`, the migration writes no history event of its own, the numbers are untouched and every hash chain still verifies; entries written afterwards
follow the new rules.
"""
import os
import subprocess
import sys
import uuid
from datetime import date, timedelta

import psycopg
import pytest

from .conftest import BACKEND, TEST_DB_URL
from .test_migration_0052 import _fill

SCRATCH = "veekay_mig0053"


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
        _alembic("0052", sa_url)
        yield scratch_url, sa_url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def test_existing_entries_start_submitted_and_reviewed_marks_become_reviewed_l3(scratch):
    url, sa_url = scratch
    org, plat, store, emp, rev = (uuid.uuid4() for _ in range(5))
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(4)]
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.cursor()
        _fill(cur, "organizations", id=org, slug="veekay", name="V", kind="internal")
        _fill(cur, "organizations", id=plat, slug="blinkit", name="Blinkit", kind="partner")
        for uid, code in ((emp, "E1"), (rev, "R1")):
            _fill(cur, "users", id=uid, organization_id=org, employee_code=code, full_name=f"User {code}", password_hash="x")
        _fill(cur, "stores", id=store, organization_id=org, partner_organization_id=plat, name="Mart", external_code="M-1")
        for i, d in enumerate(days):
            _fill(cur, "order_entries", organization_id=org, store_id=store, order_date=d, bottle_count=10 + i, cash_adjustment=0, source="employee", marked_by_user_id=emp)
        # a reviewer marked the 2nd entry `reviewed` and flagged the 3rd under 0052
        cur.execute("SELECT set_config('app.actor_id', %s, false)", (str(rev),))
        cur.execute("UPDATE order_entries SET review_status = 'reviewed' WHERE order_date = %s", (days[1],))
        cur.execute("UPDATE order_entries SET review_status = 'flagged' WHERE order_date = %s", (days[2],))
        cur.execute("SELECT set_config('app.actor_id', '', false)")
        cur.execute("SELECT count(*) FROM order_entry_events")
        events_before = cur.fetchone()[0]

    _alembic("0053", sa_url)

    with psycopg.connect(url, autocommit=True) as c:
        cur = c.cursor()
        cur.execute("SELECT order_date, verification_status, bottle_count, l3_reviewed_by_user_id, check_requested_at FROM order_entries ORDER BY order_date")
        rows = cur.fetchall()
        assert [r[1] for r in rows] == ["submitted", "reviewed_l3", "submitted", "submitted"]
        assert [r[2] for r in rows] == [10, 11, 12, 13]                       # no number was touched
        assert rows[1][3] == rev and all(r[4] is None for r in rows)
        cur.execute("SELECT count(*) FROM order_entry_events")
        assert cur.fetchone()[0] == events_before                              # the migration wrote no history of its own
        cur.execute("SELECT bool_and(entry_verify_chain(id)) FROM order_entries")
        assert cur.fetchone()[0] is True

        # new writes follow the new rules: a contributor's entry is submitted, a Reviewer's number finalises it, and the state is in the history
        cur.execute("INSERT INTO user_roles (user_id, role_id, created_at, updated_at) SELECT %s, id, now(), now() FROM roles WHERE code = 'entry_reviewer'", (rev,))
        cur.execute("SELECT set_config('app.actor_id', %s, false)", (str(rev),))
        cur.execute("UPDATE order_entries SET bottle_count = 99 WHERE order_date = %s", (days[0],))
        cur.execute("SELECT verification_status, l3_reviewed_by_user_id FROM order_entries WHERE order_date = %s", (days[0],))
        assert cur.fetchone() == ("reviewed_l3", rev)
        cur.execute("SELECT event_type FROM order_entry_events e JOIN order_entries o ON o.id = e.entry_id WHERE o.order_date = %s ORDER BY seq", (days[0],))
        assert [r[0] for r in cur.fetchall()] == ["CREATED", "EDITED", "REVIEWED_L3"]


def test_the_migration_is_forward_only():
    import importlib.util

    spec = importlib.util.spec_from_file_location("m0053", BACKEND / "alembic" / "versions" / "0053_entry_verification_workflow.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(RuntimeError, match="forward-only"):
        mod.downgrade()
