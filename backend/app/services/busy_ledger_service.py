"""
Read side of the vendor payments tab. Every figure is computed from the ledger on each read (grouped queries), never kept in a second table,
so it is correct the moment an import commits.

Per vendor and calendar month (a month is the entry's own calendar date; "this month" is read on the Asia/Kolkata clock):
    month_total = bills in the month                    paid    = payments in the month
    pending     = month_total - paid
    opening     = vendor opening_balance + all bills - all payments before the 1st of the month
    closing     = opening + month_total - paid
Entries dated before the vendor's opening_date are already inside its opening balance, so they are not counted again in the carry-over.
Months before opening_date start from 0 (the opening balance does not exist yet).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.busy_ledger import BILL, PAYMENT, STATUS_PARTIAL, STATUS_SUCCESS, BusyLedgerEntry as L, BusySyncLog, BusyVendor as V
from app.schemas.busy_ledger import (
    Freshness, LedgerEntryOut, MonthFigures, SummaryPage, SummaryRow, SummaryTotals, VendorChoice, VendorDetail,
)

ZERO = Decimal("0")
MAX_ENTRIES_SHOWN = 1000
DEFAULT_HISTORY_MONTHS = 12
MAX_HISTORY_MONTHS = 24
SORTS = ("name", "city", "code", "month_total", "paid", "pending", "closing")


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.DISPLAY_TIMEZONE)
    except Exception:  # noqa: BLE001 - a bad setting must not take the page down
        return ZoneInfo("Asia/Kolkata")


def current_month(now: datetime | None = None) -> str:
    """This month as YYYY-MM on the Asia/Kolkata clock (not the server's)."""
    moment = (now or datetime.now(timezone.utc)).astimezone(_tz())
    return f"{moment.year:04d}-{moment.month:02d}"


def parse_month(text: str) -> date:
    """The 1st day of a 'YYYY-MM' month. ValueError for anything else."""
    try:
        year, month = text.split("-")
        if len(year) != 4 or len(month) != 2:
            raise ValueError
        return date(int(year), int(month), 1)
    except ValueError as exc:
        raise ValueError("month must look like 2026-10") from exc


def _next_month(first: date) -> date:
    return date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)


def _prev_month(first: date) -> date:
    return date(first.year - 1, 12, 1) if first.month == 1 else date(first.year, first.month - 1, 1)


def _label(first: date) -> str:
    return f"{first.year:04d}-{first.month:02d}"


def _cent(value: Decimal | int | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


# ---- all vendors ----------------------------------------------------------------

def _sum_where(*conditions):
    return func.coalesce(func.sum(L.amount).filter(and_(*conditions)), 0)


def _figures_subquery(first: date):
    """One row per active vendor with every figure of the month, from one grouped query."""
    end = _next_month(first)
    in_month = and_(L.entry_date >= first, L.entry_date < end)
    carried = and_(L.entry_date < first, or_(V.opening_date.is_(None), L.entry_date >= V.opening_date))
    base = case((or_(V.opening_date.is_(None), V.opening_date <= first), V.opening_balance), else_=0)
    grouped = (
        select(
            V.vendor_code.label("code"), V.name.label("name"), V.city.label("city"), base.label("base"),
            _sum_where(L.entry_type == BILL, in_month).label("month_total"), _sum_where(L.entry_type == PAYMENT, in_month).label("paid"),
            _sum_where(L.entry_type == BILL, carried).label("carried_bills"), _sum_where(L.entry_type == PAYMENT, carried).label("carried_payments"),
        )
        .select_from(V).outerjoin(L, and_(L.vendor_code == V.vendor_code, L.entry_date < end))
        .where(V.is_active.is_(True)).group_by(V.id).subquery("grouped")
    )
    g = grouped.c
    return select(
        g.code, g.name, g.city, g.month_total, g.paid, (g.month_total - g.paid).label("pending"),
        (g.base + g.carried_bills - g.carried_payments + g.month_total - g.paid).label("closing"),
    ).subquery("figures")


def summary(db: Session, month: str, *, sort: str = "name", descending: bool = False, page: int = 1, page_size: int = 25) -> SummaryPage:
    f = _figures_subquery(parse_month(month)).c
    columns = {"name": func.lower(f.name), "city": func.lower(func.coalesce(f.city, "")), "code": f.code, "month_total": f.month_total,
               "paid": f.paid, "pending": f.pending, "closing": f.closing}
    key = columns.get(sort, columns["name"])
    rows = db.execute(
        select(f.code, f.name, f.city, f.month_total, f.paid, f.pending, f.closing)
        .order_by(key.desc() if descending else key.asc(), f.code).limit(page_size).offset((page - 1) * page_size)
    ).all()
    count, month_total, paid, pending, closing = db.execute(
        select(func.count(), func.coalesce(func.sum(f.month_total), 0), func.coalesce(func.sum(f.paid), 0),
               func.coalesce(func.sum(f.pending), 0), func.coalesce(func.sum(f.closing), 0))
    ).one()
    return SummaryPage(
        month=month, page=page, page_size=page_size, total=count,
        items=[SummaryRow(vendor_code=r.code, name=r.name, city=r.city, month_total=_cent(r.month_total), paid=_cent(r.paid),
                          pending=_cent(r.pending), closing=_cent(r.closing)) for r in rows],
        totals=SummaryTotals(vendors=count, month_total=_cent(month_total), paid=_cent(paid), pending=_cent(pending), closing=_cent(closing)),
    )


def search_vendors(db: Session, query: str, limit: int = 20) -> list[VendorChoice]:
    """Active vendors whose name, city or code contains the text (a blank search lists the first few)."""
    stmt = select(V).where(V.is_active.is_(True))
    text = query.strip()
    if text:
        like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(V.name.ilike(like, escape="\\"), V.city.ilike(like, escape="\\"), V.vendor_code.ilike(like, escape="\\")))
    return [VendorChoice(vendor_code=v.vendor_code, name=v.name, city=v.city) for v in db.scalars(stmt.order_by(func.lower(V.name)).limit(limit))]


# ---- one vendor ---------------------------------------------------------------------

def vendor_detail(db: Session, vendor: V, month: str, months: int = DEFAULT_HISTORY_MONTHS) -> VendorDetail:
    chosen = parse_month(month)
    months = max(1, min(months, MAX_HISTORY_MONTHS))
    firsts = [chosen]
    for _ in range(months - 1):
        firsts.insert(0, _prev_month(firsts[0]))
    window_start, end = firsts[0], _next_month(chosen)
    counted_from = vendor.opening_date

    carried = {t: ZERO for t in (BILL, PAYMENT)}
    carry_query = select(L.entry_type, func.sum(L.amount)).where(L.vendor_code == vendor.vendor_code, L.entry_date < window_start)
    if counted_from:
        carry_query = carry_query.where(L.entry_date >= counted_from)
    carried.update({t: total for t, total in db.execute(carry_query.group_by(L.entry_type)).all()})

    label = func.to_char(L.entry_date, "YYYY-MM")
    by_month: dict[tuple[str, str], Decimal] = {
        (m, t): total for m, t, total in db.execute(
            select(label, L.entry_type, func.sum(L.amount))
            .where(L.vendor_code == vendor.vendor_code, L.entry_date >= window_start, L.entry_date < end).group_by(label, L.entry_type)
        ).all()
    }

    running = carried[BILL] - carried[PAYMENT]
    history: list[MonthFigures] = []
    for first in firsts:
        bills, paid = by_month.get((_label(first), BILL), ZERO), by_month.get((_label(first), PAYMENT), ZERO)
        applies = counted_from is None or counted_from <= first
        opening = (vendor.opening_balance if applies else ZERO) + running
        history.append(MonthFigures(month=_label(first), opening=_cent(opening), month_total=_cent(bills), paid=_cent(paid),
                                    pending=_cent(bills - paid), closing=_cent(opening + bills - paid)))
        if applies:
            running += bills - paid

    shown = list(db.scalars(
        select(L).where(L.vendor_code == vendor.vendor_code, L.entry_date >= chosen, L.entry_date < end)
        .order_by(L.entry_date, L.entry_type, L.voucher_no).limit(MAX_ENTRIES_SHOWN + 1)
    ))
    return VendorDetail(
        vendor=VendorChoice(vendor_code=vendor.vendor_code, name=vendor.name, city=vendor.city),
        month=history[-1], history=history,
        entries=[LedgerEntryOut.model_validate(e) for e in shown[:MAX_ENTRIES_SHOWN]], entries_truncated=len(shown) > MAX_ENTRIES_SHOWN,
    )


# ---- freshness ----------------------------------------------------------------------

def freshness(db: Session, now: datetime | None = None) -> Freshness:
    now = now or datetime.now(timezone.utc)
    last = db.execute(
        select(BusySyncLog.finished_at, BusySyncLog.source).where(BusySyncLog.status.in_((STATUS_SUCCESS, STATUS_PARTIAL)), BusySyncLog.finished_at.is_not(None))
        .order_by(BusySyncLog.finished_at.desc()).limit(1)
    ).first()
    limit = settings.BUSY_STALE_HOURS
    if last is None:
        return Freshness(last_updated=None, last_source=None, age_minutes=None, stale=True, stale_hours=limit, never_synced=True)
    age = now - last.finished_at
    return Freshness(last_updated=last.finished_at, last_source=last.source, age_minutes=max(0, int(age.total_seconds() // 60)),
                     stale=age > timedelta(hours=limit), stale_hours=limit, never_synced=False)
