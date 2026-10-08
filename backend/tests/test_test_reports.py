"""Test reports: per platform + state, six-month validity, expiry status, replace / remove, access."""
from datetime import date

import pytest

from app.models.test_report import TestReport
from app.services import test_report_service as svc

from .conftest import API, PDF_BYTES, jpeg

STATE = "Testland-Z"


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(TestReport).filter(TestReport.state.like("Testland%")).delete(synchronize_session=False)
    db.commit()


def _months_ago(n: int) -> str:
    t = date.today()
    idx = t.year * 12 + t.month - 1 - n
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def _up(client, headers, *, partner="zepto", state=STATE, period=None, file=None):
    file = file or ("r.pdf", PDF_BYTES, "application/pdf")
    return client.post(f"{API}/test-reports", headers=headers,
                       data={"partner": partner, "state": state, "period_start": period or _months_ago(0)}, files={"file": file})


def _row(client, headers, state=STATE, partner="zepto"):
    r = client.get(f"{API}/test-reports?partner={partner}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json(), next((s for s in r.json()["states"] if s["state"] == state), None)


def test_a_period_covers_six_months_counting_the_start_month():
    assert svc.period_end_for(date(2026, 10, 1)) == date(2027, 3, 31)
    assert svc.period_end_for(date(2026, 1, 1)) == date(2026, 6, 30)
    assert svc.period_end_for(date(2026, 9, 1)) == date(2027, 2, 28)


def test_only_zepto_is_switched_on_and_blinkit_is_off(client, admin, make_store):
    make_store(code="TR-Z1", platform="zepto", region=None, state=STATE)
    body, row = _row(client, admin)
    assert body["platform"]["enabled"] is True
    assert {p["slug"]: p["enabled"] for p in body["platforms"]} == {"blinkit": False, "zepto": True}
    assert row["status"] == "MISSING" and row["stores"] == 1 and row["current"] is None

    blink, none = _row(client, admin, partner="blinkit")
    assert blink["platform"]["enabled"] is False and blink["states"] == []
    r = _up(client, admin, partner="blinkit")
    assert r.status_code == 422 and "not enabled" in r.json()["detail"]


def test_upload_makes_a_state_valid_and_computes_the_end_date(client, admin, make_store):
    make_store(code="TR-Z2", platform="zepto", region=None, state=STATE)
    r = _up(client, admin, period=_months_ago(0))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "VALID" and out["period_end"] > date.today().isoformat() and out["days_left"] > 100

    body, row = _row(client, admin)
    assert row["status"] == "VALID" and row["current"]["id"] == out["id"] and row["history"] == []
    assert body["summary"]["reports_total"] >= 1 and body["summary"]["states_total"] >= 1


def test_expired_and_expiring_reports_are_flagged(client, admin, make_store):
    make_store(code="TR-Z3", platform="zepto", region=None, state=STATE)
    make_store(code="TR-Z4", platform="zepto", region=None, state="Testland-Y")

    assert _up(client, admin, state=STATE, period=_months_ago(8)).status_code == 201         # ended 2+ months ago
    assert _up(client, admin, state="Testland-Y", period=_months_ago(5)).status_code == 201  # ends this month

    body, expired = _row(client, admin, STATE)
    _, soon = _row(client, admin, "Testland-Y")
    assert expired["status"] == "EXPIRED" and expired["current"]["days_left"] < 0
    assert soon["status"] == "EXPIRING" and 0 <= soon["current"]["days_left"] <= body["alert_days"]
    assert body["summary"]["expired"] >= 1 and body["summary"]["expiring"] >= 1
    # Problems sort first.
    order = [s["status"] for s in body["states"]]
    assert order == sorted(order, key=["EXPIRED", "EXPIRING", "MISSING", "VALID"].index)


def test_same_period_replaces_and_a_new_period_keeps_history(client, admin, make_store, db):
    make_store(code="TR-Z5", platform="zepto", region=None, state=STATE)
    first = _up(client, admin, period=_months_ago(7)).json()
    second = _up(client, admin, period=_months_ago(7), file=("b.jpg", jpeg(), "image/jpeg")).json()   # same period: replaces
    _, row = _row(client, admin)
    assert row["current"]["id"] == second["id"] and row["history"] == []
    assert db.get(TestReport, __import__("uuid").UUID(first["id"])).deleted_at is not None         # archived, not erased

    newer = _up(client, admin, period=_months_ago(0)).json()                                       # next six months
    _, row = _row(client, admin)
    assert row["current"]["id"] == newer["id"] and [h["id"] for h in row["history"]] == [second["id"]]
    assert row["status"] == "VALID"


def test_bad_input_is_refused(client, admin, make_store):
    make_store(code="TR-Z6", platform="zepto", region=None, state=STATE)
    assert _up(client, admin, state="Atlantis").status_code == 422                     # no stores there
    assert _up(client, admin, period="2026-13").status_code == 422
    assert _up(client, admin, period=_months_ago(60)).status_code == 422               # far too old
    assert _up(client, admin, file=("x.txt", b"plain text", "text/plain")).status_code == 422
    assert _up(client, admin, state=STATE.lower()).status_code == 201                  # state match ignores case


def test_view_and_remove(client, admin, make_store):
    make_store(code="TR-Z7", platform="zepto", region=None, state=STATE)
    rid = _up(client, admin).json()["id"]
    f = client.get(f"{API}/test-reports/{rid}/file", headers=admin)
    assert f.status_code == 200 and f.content.startswith(b"%PDF")
    link = client.get(f"{API}/test-reports/{rid}/url", headers=admin).json()
    assert link["url"] is None and link["content_type"] == "application/pdf"      # local disk: the app streams it

    assert client.delete(f"{API}/test-reports/{rid}", headers=admin).status_code == 204
    assert client.get(f"{API}/test-reports/{rid}/file", headers=admin).status_code == 404
    _, row = _row(client, admin)
    assert row["status"] == "MISSING"


def test_only_the_right_people_can_see_or_change_reports(client, emp, admin, make_store):
    make_store(code="TR-Z8", platform="zepto", region=None, state=STATE)
    assert client.get(f"{API}/test-reports", headers=emp).status_code == 403
    assert _up(client, emp).status_code == 403
    rid = _up(client, admin).json()["id"]
    assert client.delete(f"{API}/test-reports/{rid}", headers=emp).status_code == 403
    assert client.get(f"{API}/test-reports/{rid}/file", headers=emp).status_code == 403
    assert client.get(f"{API}/test-reports").status_code == 401
