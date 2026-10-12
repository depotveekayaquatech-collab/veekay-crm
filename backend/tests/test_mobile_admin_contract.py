"""The mobile app's admin screens read these endpoints and rely on these fields. If one changes, this fails first."""
from .conftest import API


def _keys(d: dict, *names: str):
    missing = [n for n in names if n not in d]
    assert not missing, f"missing fields {missing} in {sorted(d)}"


def test_admin_overview_reads(client, admin):
    ins = client.get(f"{API}/orders/insights", headers=admin).json()
    _keys(ins, "bottles_today", "bottles_yesterday", "entries_today", "store_status", "trend", "platforms", "attention_stores", "dormant_live", "last_store_sync")
    if ins["trend"]:
        _keys(ins["trend"][0], "date", "label", "entries", "bottles")
    if ins["platforms"]:
        _keys(ins["platforms"][0], "slug", "label", "total_stores", "entries_done", "bottles", "percent")

    pend = client.get(f"{API}/orders/pending", params={"day_offset": 0}, headers=admin).json()
    _keys(pend, "date", "date_label", "day_offset", "live_stores", "marked", "pending", "items")
    if pend["items"]:
        _keys(pend["items"][0], "id", "name", "external_code", "region_name", "poc_name", "poc_number", "pending_days")

    leaves = client.get(f"{API}/attendance/leaves", params={"status": "PENDING"}, headers=admin).json()
    _keys(leaves, "items", "pending")

    summary = client.get(f"{API}/bottles/summary", headers=admin).json()
    _keys(summary, "total_active", "at_store", "overdue", "lost_after_days")
    overdue = client.get(f"{API}/bottles", params={"state": "OVERDUE", "page": 1, "page_size": 50}, headers=admin).json()
    _keys(overdue, "items", "total", "page", "page_size")

    due = client.get(f"{API}/compliance/due", headers=admin).json()
    _keys(due, "total", "items")


def test_employee_cannot_open_the_admin_reads(client, emp):
    for path in ("/orders/insights", "/orders/pending", "/attendance/leaves", "/compliance/due"):
        assert client.get(f"{API}{path}", headers=emp).status_code == 403, path
    assert client.post(f"{API}/attendance/leaves/00000000-0000-0000-0000-000000000000/review", json={"approve": True}, headers=emp).status_code == 403


def test_leave_review_round_trip(client, admin, make_user, db):
    """An employee applies, the admin approves it from the approvals screen, and a second decision is refused."""
    from datetime import date, timedelta

    from .conftest import login

    code, pw, _ = make_user()
    h = {"Authorization": f"Bearer {login(client, code, pw).json()['access_token']}"}
    target = date.today() + timedelta(days=20)
    if target.weekday() == 6:
        target += timedelta(days=1)
    day = str(target)
    made = client.post(f"{API}/attendance/leaves", json={"leave_type": "CASUAL", "start_date": day, "end_date": day, "half_day": False, "reason": "family function"}, headers=h)
    assert made.status_code == 201, made.text
    lid = made.json()["id"]

    pending = client.get(f"{API}/attendance/leaves", params={"status": "PENDING"}, headers=admin).json()
    row = next(x for x in pending["items"] if x["id"] == lid)
    assert row["person"]["code"] == code and row["status"] == "PENDING"

    ok = client.post(f"{API}/attendance/leaves/{lid}/review", json={"approve": True, "note": "enjoy"}, headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED" and ok.json()["review_note"] == "enjoy"
    assert client.post(f"{API}/attendance/leaves/{lid}/review", json={"approve": False}, headers=admin).status_code == 409
