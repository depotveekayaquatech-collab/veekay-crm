"""Marking LAST month's dates during the first days of a month, so a month can be completed after it has ended."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.services import order_service

from .conftest import API

NOW = datetime.now(timezone.utc).date()
THIS = NOW.replace(day=1)
LAST_END = THIS - timedelta(days=1)
LAST_START = LAST_END.replace(day=1)
TWO_BACK = LAST_START - timedelta(days=1)


def _on(monkeypatch, day_of_month: int):
    """Pretend today is the Nth of this month (the server's date)."""
    monkeypatch.setattr(order_service, "_today", lambda: THIS.replace(day=day_of_month))


def _mark(client, who, store, d, n=10):
    return client.post(f"{API}/orders/mark", headers=who, json={"store_id": str(store.id), "order_date": d.isoformat(), "bottle_count": n})


def _calendar(client, who, store, y, m):
    return client.get(f"{API}/orders/calendar", headers=who, params={"store_id": str(store.id), "year": y, "month": m})


def test_during_the_grace_days_an_employee_can_mark_last_month(client, emp, db, make_store, monkeypatch):
    s = make_store(code="BM-A")
    _on(monkeypatch, 3)
    r = _mark(client, emp, s, LAST_END, 42)
    assert r.status_code == 200, r.text
    assert db.query(OrderEntry).filter(OrderEntry.store_id == s.id, OrderEntry.order_date == LAST_END).one().bottle_count == 42
    assert _mark(client, emp, s, LAST_START, 11).status_code == 200            # any day of last month
    assert _mark(client, emp, s, THIS.replace(day=2), 5).status_code == 200      # and this month, as ever
    assert _mark(client, emp, s, LAST_END, 99).status_code == 409                # still one entry per day, and an employee cannot change it
    assert _mark(client, emp, s, THIS.replace(day=9), 5).status_code == 422      # a future date is still refused


def test_the_calendar_says_whether_a_month_can_be_marked(client, emp, admin, make_store, monkeypatch):
    s = make_store(code="BM-CAL")
    _on(monkeypatch, 3)
    last = _calendar(client, emp, s, LAST_END.year, LAST_END.month).json()
    assert last["can_mark"] is True and last["open_until"] == THIS.replace(day=settings.BACKMONTH_GRACE_DAYS).isoformat()
    this = _calendar(client, emp, s, THIS.year, THIS.month).json()
    assert this["can_mark"] is True and this["open_until"] is None
    older = _calendar(client, emp, s, TWO_BACK.year, TWO_BACK.month).json()
    assert older["can_mark"] is False                                               # two months back: view only
    assert _calendar(client, admin, s, TWO_BACK.year, TWO_BACK.month).json()["can_mark"] is True    # admins can always mark


def test_after_the_grace_days_last_month_is_closed_with_a_clear_reason(client, emp, make_store, monkeypatch):
    s = make_store(code="BM-LATE")
    _on(monkeypatch, settings.BACKMONTH_GRACE_DAYS + 1)
    r = _mark(client, emp, s, LAST_END)
    assert r.status_code == 422 and "Last month's entries could only be added until" in r.json()["detail"]
    cal = _calendar(client, emp, s, LAST_END.year, LAST_END.month).json()
    assert cal["can_mark"] is False


def test_two_months_back_is_never_open_to_an_employee_and_the_feature_can_be_switched_off(client, emp, make_store, monkeypatch):
    s = make_store(code="BM-OFF")
    _on(monkeypatch, 2)
    assert _mark(client, emp, s, TWO_BACK).status_code == 422
    monkeypatch.setattr(settings, "BACKMONTH_GRACE_DAYS", 0)
    r = _mark(client, emp, s, LAST_END)
    assert r.status_code == 422 and "can no longer be added" in r.json()["detail"]
    assert _calendar(client, emp, s, LAST_END.year, LAST_END.month).json()["can_mark"] is False


def test_the_grace_period_follows_the_setting(client, emp, make_store, monkeypatch):
    s = make_store(code="BM-SET")
    monkeypatch.setattr(settings, "BACKMONTH_GRACE_DAYS", 3)
    _on(monkeypatch, 3)
    assert _mark(client, emp, s, LAST_END).status_code == 200
    _on(monkeypatch, 4)
    assert _mark(client, emp, s, LAST_START).status_code == 422


def test_mark_many_can_fill_several_days_of_last_month_at_once(client, emp, db, make_store, monkeypatch):
    s = make_store(code="BM-MANY")
    _on(monkeypatch, 4)
    days = [LAST_END - timedelta(days=i) for i in range(3)]
    body = {"store_id": str(s.id), "entries": [{"order_date": d.isoformat(), "bottle_count": 10 + i} for i, d in enumerate(days)]}
    out = client.post(f"{API}/orders/mark-many", headers=emp, json=body).json()
    assert (out["saved"], out["failed"]) == (3, 0)


def test_my_stores_says_how_many_days_of_last_month_are_still_missing_while_it_is_open(client, emp, admin, db, make_store, monkeypatch):
    s, done = make_store(code="BM-MISS"), make_store(code="BM-FULL")
    days_last = (LAST_END - LAST_START).days + 1
    for i in range(days_last):
        db.add(OrderEntry(organization_id=done.organization_id, store_id=done.id, order_date=LAST_START + timedelta(days=i), bottle_count=1, source="employee"))
    for i in range(10):                                                           # 10 days filled, the rest missing
        db.add(OrderEntry(organization_id=s.organization_id, store_id=s.id, order_date=LAST_START + timedelta(days=i), bottle_count=1, source="employee"))
    db.commit()
    _on(monkeypatch, 2)
    for who in (emp, admin):
        got = {x["external_code"]: x for x in client.get(f"{API}/orders/my-stores", headers=who).json()}
        assert got["BM-MISS"]["last_month_missing"] == days_last - 10
        assert got["BM-FULL"]["last_month_missing"] == 0
        assert got["BM-MISS"]["last_month_open_until"] == THIS.replace(day=settings.BACKMONTH_GRACE_DAYS).isoformat()
    # a store that started part-way through last month is only behind from its start date
    late = make_store(code="BM-START")
    late.start_date = LAST_START + timedelta(days=days_last - 5)                  # started 5 days before the month ended
    db.commit()
    got = {x["external_code"]: x for x in client.get(f"{API}/orders/my-stores", headers=emp).json()}
    assert got["BM-START"]["last_month_missing"] == 5
    # once the window has closed nothing is reported
    _on(monkeypatch, settings.BACKMONTH_GRACE_DAYS + 2)
    closed = {x["external_code"]: x for x in client.get(f"{API}/orders/my-stores", headers=emp).json()}
    assert closed["BM-MISS"]["last_month_missing"] == 0 and closed["BM-MISS"]["last_month_open_until"] is None
