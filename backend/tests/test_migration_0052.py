"""Migration 0052 on realistic OLD data: a scratch database is migrated to 0051, filled with entries written the old way, then upgraded.

The promise being proven: a creator is filled in ONLY where the activity log proves it; every other entry stays unverified with no creator (never
guessed), keeps its old "last recorded marker", and gets a BASELINE event; nothing is deleted; the hash chain of every entry verifies.
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from .conftest import BACKEND, TEST_DB_URL

SCRATCH = "veekay_mig0052"


def _urls():
    plain = TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _ = plain.rpartition("/")
    return f"{base}/postgres", f"{base}/{SCRATCH}", f"postgresql+psycopg://{base.split('://', 1)[1]}/{SCRATCH}"


def _alembic(target: str, sa_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": sa_url}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", target], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def _fill(cur, table, **given):
    """INSERT one row giving only what matters; every other NOT NULL column without a default gets a neutral value of its type."""
    cur.execute("SELECT column_name, data_type, is_nullable, column_default, is_identity FROM information_schema.columns WHERE table_name = %s", (table,))
    cols = dict(given)
    for name, typ, nullable, default, ident in cur.fetchall():
        if name in cols or nullable == "YES" or default is not None or ident == "YES":
            continue
        cols[name] = {"uuid": uuid.uuid4(), "text": "x", "character varying": "x", "integer": 0, "boolean": False, "date": date.today(),
                      "timestamp with time zone": datetime.now(timezone.utc), "bigint": 0, "jsonb": json.dumps({})}[typ]
    keys = list(cols)
    cur.execute(f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})",
                [json.dumps(v) if isinstance(v, dict) else v for v in cols.values()])


@pytest.fixture()
def scratch():
    admin_url, scratch_url, sa_url = _urls()
    with psycopg.connect(admin_url, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {SCRATCH}")
    try:
        _alembic("0051", sa_url)
        yield scratch_url, sa_url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as c:
            c.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")


def test_old_entries_get_a_creator_only_when_the_activity_log_proves_it(scratch):
    url, sa_url = scratch
    org, plat, store = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    emp, other, adm = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    d1, d2, d3, d4, d5 = (date(2026, 9, 1) + timedelta(days=i) for i in range(5))
    ids = {k: uuid.uuid4() for k in "12345"}
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.cursor()
        _fill(cur, "organizations", id=org, slug="veekay", name="V", kind="internal")
        _fill(cur, "organizations", id=plat, slug="blinkit", name="Blinkit", kind="partner")
        for uid, code in ((emp, "E1"), (other, "E2"), (adm, "ADM")):
            _fill(cur, "users", id=uid, organization_id=org, employee_code=code, full_name=f"User {code}", password_hash="x")
        _fill(cur, "stores", id=store, organization_id=org, partner_organization_id=plat, name="Mart", external_code="M-1")

        def entry(key, day, count, source, marker):
            _fill(cur, "order_entries", id=ids[key], organization_id=org, store_id=store, order_date=day, bottle_count=count, cash_adjustment=0,
                  source=source, marked_by_user_id=marker)

        def log(day, user, action="order.marked"):
            _fill(cur, "audit_logs", user_id=user, organization_id=org, action=action, entity_type="order_entry", entity_id=str(store),
                  metadata_json={"order_date": day.isoformat()})

        entry("1", d1, 10, "employee", emp);   log(d1, emp)                                  # proven: the log says E1 marked it and E1 is still the marker
        entry("2", d2, 20, "employee", emp);   log(d2, other)                                # the log says someone ELSE marked it last: not proven
        entry("3", d3, 30, "admin", adm);      log(d3, emp)                                  # an admin rewrote it since: not proven
        entry("4", d4, 40, "employee", emp)                                                  # no log at all (purged / imported): not proven
        entry("5", d5, 50, "employee", other); log(d5, other); log(d5, emp)                  # latest mark wins: 'other' is the marker and made the latest mark? (emp logged later)
        cur.execute("UPDATE audit_logs SET created_at = created_at + interval '1 hour' WHERE user_id = %s AND metadata_json->>'order_date' = %s", (emp, d5.isoformat()))

    _alembic("0052", sa_url)

    with psycopg.connect(url) as c:
        cur = c.cursor()
        cur.execute("SELECT id, created_by_user_id, creator_verified, created_via, created_by_code, marked_by_user_id, version, review_status FROM order_entries")
        rows = {r[0]: r for r in cur.fetchall()}
        assert len(rows) == 5                                                                # nothing deleted
        r1 = rows[ids["1"]]
        assert r1[1] == emp and r1[2] is True and r1[3] == "verified_from_activity_log" and r1[4] == "E1"
        for k in "2345":
            r = rows[ids[k]]
            assert r[1] is None and r[2] is False and r[3] == "legacy_unverified", k          # never guessed
        assert rows[ids["2"]][5] == emp and rows[ids["3"]][5] == adm and rows[ids["5"]][5] == other   # the old marker is kept for the investigation
        assert all(r[6] == 1 and r[7] == "none" for r in rows.values())

        cur.execute("SELECT entry_id, event_type, actor_user_id, actor_known, reason, new_values FROM order_entry_events")
        events = {}
        for e in cur.fetchall():
            events.setdefault(e[0], []).append(e)
        assert all(len(v) == 1 and v[0][1] == "BASELINE" for v in events.values()) and len(events) == 5
        assert events[ids["1"]][0][2] == emp and events[ids["1"]][0][3] is True and "proven" in events[ids["1"]][0][4]
        assert events[ids["4"]][0][2] is None and events[ids["4"]][0][3] is False and "NOT verified" in events[ids["4"]][0][4]
        assert events[ids["4"]][0][5]["bottle_count"] == 40 and events[ids["4"]][0][5]["last_recorded_marker"] == str(emp)
        for k in ids.values():
            cur.execute("SELECT entry_verify_chain(%s)", (k,))
            assert cur.fetchone()[0] is True                                                  # the baseline events chain correctly

        # the new roles and permissions exist, and nobody was promoted
        cur.execute("SELECT code FROM roles WHERE code IN ('team_lead','entry_reviewer') ORDER BY code")
        assert [r[0] for r in cur.fetchall()] == ["entry_reviewer", "team_lead"]
        cur.execute("SELECT count(*) FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code IN ('team_lead','entry_reviewer')")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM users WHERE reports_to_user_id IS NOT NULL")
        assert cur.fetchone()[0] == 0

        # and from now on a change is recorded by the trigger: the old row's first edit chains onto its baseline
        cur.execute("SELECT set_config('app.actor_id', %s, false)", (str(adm),))
        cur.execute("SELECT set_config('app.reason', 'checked against the delivery note', false)")
        cur.execute("UPDATE order_entries SET bottle_count = 41, source = 'admin' WHERE id = %s", (ids["4"],))
        cur.execute("SELECT event_type, entry_version, reason, actor_user_id FROM order_entry_events WHERE entry_id = %s ORDER BY seq", (ids["4"],))
        got = cur.fetchall()
        assert [g[0] for g in got] == ["BASELINE", "EDITED"] and got[1][1] == 2 and got[1][3] == adm and got[1][2].startswith("checked")
        cur.execute("SELECT entry_verify_chain(%s)", (ids["4"],))
        assert cur.fetchone()[0] is True
        cur.execute("SELECT created_by_user_id, creator_verified FROM order_entries WHERE id = %s", (ids["4"],))
        assert cur.fetchone() == (None, False)                                                # editing never invents a creator
        c.rollback()
