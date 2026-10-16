"""
"Was this store active in that month?"  One rule, used by every month-filtered store list.

A store is active in month M when it had begun being supplied by the END of M: its start date is on or before the last day
of M. A store with no start date yet is kept (nothing is hidden until orders or the sheet say when it started). A store
that started in a LATER month is not shown for M. Older stores always stay, whichever vendor supplied them then.
"""
from __future__ import annotations

import calendar
from datetime import date

from app.models.store import Store


def month_start(month: date) -> date:
    return date(month.year, month.month, 1)


def month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def active_in_month(store: Store, month: date) -> bool:
    return store.start_date is None or store.start_date <= month_end(month)


def filter_active_in_month(stores: list[Store], month: date | None) -> list[Store]:
    """`month=None` means no month was chosen: nothing is filtered."""
    return stores if month is None else [s for s in stores if active_in_month(s, month)]
