"""The admin dashboard's "Bottles today" / "Entries today": what people marked TODAY (India time), whatever order date they marked.
(They used to count entries whose order date is today, which reads 0 all day when employees enter the previous day's orders.)"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core import audit_context
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order_entry import OrderEntry
from app.repositories.order_entry_repository import OrderEntryRepository

from .conftest import API

TZ = "Asia/Kolkata"
UTC = timezone.utc


@pytest.fixture(autouse=True)
def _no_dashboard_cache(monkeypatch):
    """Entries planted straight into the database do not clear the shared dashboard cache the way an API write does."""
    monkeypatch.setattr(settings, "DASHBOARD_CACHE_SECONDS", 0)


def _insights(client, admin, **params):
    return client.get(f"{API}/orders/insights", headers=admin, params=params).json()


def _plant(store, created_at, count, *, cash=0, via=None, order_date=None):
    """An entry as the database would hold it, with a chosen creation moment. No actor is bound, so the creation time is kept as given."""
    with SessionLocal() as s:
        if via:
            audit_context.bind(s, None, source=via)
        s.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=order_date or created_at.date(), bottle_count=count + cash,
                         cash_adjustment=cash, source="employee", created_at=created_at))
        s.commit()


def test_marking_yesterdays_orders_today_counts_as_today(client, admin, emp, make_store):
    store = make_store()
    yesterday = date.today() - timedelta(days=1)
    before = _insights(client, admin)
    marked = client.post(f"{API}/orders/mark-many", json={"store_id": str(store.id), "entries": [{"order_date": str(yesterday), "bottle_count": 17}]}, headers=emp)
    assert marked.status_code == 200 and marked.json()["saved"] == 1

    after = _insights(client, admin)
    assert after["entries_today"] == before["entries_today"] + 1
    assert after["bottles_today"] == before["bottles_today"] + 17
    assert after["trend"][-1]["entries"] == before["trend"][-1]["entries"]            # the chart is still by order date: nothing was ordered for today
    assert after["trend"][-2]["entries"] == before["trend"][-2]["entries"] + 1


def test_the_platform_filter_only_counts_that_platforms_marks(client, admin, emp, make_store):
    blinkit = make_store(platform="blinkit")
    before = {slug: _insights(client, admin, partner=slug)["entries_today"] for slug in ("blinkit", "zepto")}
    client.post(f"{API}/orders/mark-many", json={"store_id": str(blinkit.id), "entries": [{"order_date": str(date.today()), "bottle_count": 5}]}, headers=emp)
    assert _insights(client, admin, partner="blinkit")["entries_today"] == before["blinkit"] + 1
    assert _insights(client, admin, partner="zepto")["entries_today"] == before["zepto"]


def test_yesterdays_marks_feed_the_comparison(client, admin, make_store):
    store = make_store()
    yesterday_noon_ist = datetime.now(UTC) - timedelta(days=1)
    before = _insights(client, admin)["bottles_yesterday"]
    _plant(store, yesterday_noon_ist, 40)
    assert _insights(client, admin)["bottles_yesterday"] == before + 40


def test_the_day_is_the_india_day_not_the_utc_day(db, make_store):
    store = make_store()
    _plant(store, datetime(2026, 3, 10, 18, 15, tzinfo=UTC), 7)        # 23:45 on 10 March in India
    _plant(store, datetime(2026, 3, 10, 18, 45, tzinfo=UTC), 11, order_date=date(2026, 3, 9))       # 00:15 on 11 March in India
    start = datetime(2026, 3, 9, 18, 30, tzinfo=UTC)                    # 10 March 00:00 India
    end = datetime(2026, 3, 11, 18, 30, tzinfo=UTC)                     # 12 March 00:00 India
    per_day = OrderEntryRepository(db).marked_per_day(store.organization_id, start, end, TZ)
    assert per_day[date(2026, 3, 10)] == (1, 7) and per_day[date(2026, 3, 11)] == (1, 11)
    assert OrderEntryRepository(db).marked_per_day(store.organization_id, start, datetime(2026, 3, 10, 18, 30, tzinfo=UTC), TZ)[date(2026, 3, 10)] == (1, 7)


def test_bottles_are_what_the_employee_entered_not_the_cash_adjustment(db, make_store):
    store = make_store()
    when = datetime(2026, 3, 12, 6, 0, tzinfo=UTC)
    _plant(store, when, 15, cash=5)                                      # final count 20, of which 5 came from a developer's cash adjustment
    per_day = OrderEntryRepository(db).marked_per_day(store.organization_id, when - timedelta(hours=1), when + timedelta(hours=1), TZ)
    assert per_day[date(2026, 3, 12)] == (1, 15)


def test_bulk_imports_are_not_somebody_marking(db, make_store):
    store_a, store_b, store_c = make_store(), make_store(), make_store()
    when = datetime(2026, 3, 13, 5, 0, tzinfo=UTC)
    _plant(store_a, when, 10)
    _plant(store_b, when, 99, via="sheet_sync_scheduled")
    _plant(store_c, when, 98, via="order_sheet_import_file")
    per_day = OrderEntryRepository(db).marked_per_day(store_a.organization_id, when - timedelta(hours=1), when + timedelta(hours=1), TZ)
    assert per_day[date(2026, 3, 13)] == (1, 10)
    assert Decimal(per_day[date(2026, 3, 13)][1]) == Decimal(10)


def test_nothing_marked_reads_zero_not_an_error(db, make_store):
    store = make_store()
    assert OrderEntryRepository(db).marked_per_day(store.organization_id, datetime(2001, 1, 1, tzinfo=UTC), datetime(2001, 1, 2, tzinfo=UTC), TZ) == {}
