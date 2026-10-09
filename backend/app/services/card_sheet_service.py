"""
Cards from an uploaded sheet (developer-only for now, behind an access code).

A sheet of  store / date / filled bottles  rows becomes the same A4 monthwise store cards the Store cards page makes,
filled with the sheet's entries instead of the order records. Nothing is written to the orders. Every page carries a
"Source: uploaded sheet" footer (file name, who, when), and every unlock, preview and download is in the audit log.

Access is two-step: the `cards.sheet` permission (reserved, so only the developer role has it for now) AND a code that
the server checks. Unlocking gives a 30 minute token tied to the user; five wrong codes lock the user out for 15 minutes.
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import io
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.organization import Organization
from app.models.store import Store
from app.models.user import User
from app.services import activity_service, card_service

TOKEN_TTL_SECONDS = 30 * 60
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
MAX_CARDS = 600
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_COUNT = 100000

_fails: dict[uuid.UUID, tuple[int, float]] = {}      # user id -> (wrong tries, locked until epoch)

# Header names are compared after lower-casing and dropping everything but letters and digits, so "Outlet ID",
# "outlet_id" and "OUTLET-ID" are all the same. Add an alias here when a sheet starts using a new word.
_ALIASES = {
    "code": ("outletid", "outletcode", "storeid", "storecode", "externalcode", "outlet", "code", "id"),
    "name": ("outletname", "storename", "name", "store"),
    "date": ("date", "orderdate", "deliverydate", "day"),
    "count": ("filledbottles", "filled", "bottles", "bottlecount", "count", "qty", "quantity", "delivered"),
    "platform": ("platform", "channel", "partner"),
}
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%Y/%m/%d", "%m/%d/%Y")


# --------------------------------------------------------------------------
# the access code
# --------------------------------------------------------------------------

def _key() -> bytes:
    return hashlib.sha256(b"cardsheet|" + (settings.QR_SIGNING_SECRET or settings.JWT_SECRET_KEY).encode()).digest()


def _sign(user_id: uuid.UUID, expires: int) -> str:
    body = f"{user_id}|{expires}"
    sig = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def check_token(user: User, token: str | None) -> None:
    """403 unless the token is genuine, belongs to this user and hasn't expired."""
    locked = HTTPException(status.HTTP_403_FORBIDDEN, "Locked. Enter the access code.")
    try:
        raw = base64.urlsafe_b64decode((token or "").encode())
        uid, exp, sig = raw.decode().split("|")
        expected = hmac.new(_key(), f"{uid}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        valid = (
            base64.urlsafe_b64encode(raw).decode() == token      # exactly what we issued, no trailing junk
            and hmac.compare_digest(sig, expected) and uid == str(user.id) and int(exp) >= time.time()
        )
    except Exception:  # noqa: BLE001 - any malformed token is simply locked
        valid = False
    if not valid:
        raise locked


def unlock(db: Session, user: User, code: str) -> dict:
    now = time.time()
    tries, until = _fails.get(user.id, (0, 0.0))
    if until > now:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many wrong codes. Try again in {int((until - now) // 60) + 1} minutes.")
    if not hmac.compare_digest((code or "").strip().encode(), settings.CARD_SHEET_CODE.encode()):
        tries += 1
        _fails[user.id] = (tries, now + LOCK_SECONDS if tries >= MAX_FAILS else 0.0)
        if tries >= MAX_FAILS:
            _fails[user.id] = (0, now + LOCK_SECONDS)
        activity_service.record(db, actor=user, action="card_sheet.unlock_failed", entity_type="card_sheet", entity_id=user.id, metadata={"tries": tries})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That code isn't right.")
    _fails.pop(user.id, None)
    expires = int(now) + TOKEN_TTL_SECONDS
    activity_service.record(db, actor=user, action="card_sheet.unlocked", entity_type="card_sheet", entity_id=user.id, metadata={})
    db.commit()
    return {"token": _sign(user.id, expires), "expires_in": TOKEN_TTL_SECONDS}


# --------------------------------------------------------------------------
# reading the sheet
# --------------------------------------------------------------------------

@dataclass
class SheetCard:
    store: Store
    month: date
    entries: dict[date, int] = field(default_factory=dict)


@dataclass
class Parsed:
    cards: list[SheetCard]
    unmatched: list[dict]           # {row, store, reason}
    warnings: list[str]
    rows: int
    filename: str
    sha256: str


def _norm_header(text: object) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _grids(filename: str, content: bytes) -> list[list[list[str]]]:
    """Every sheet of the file as a grid of text cells (a CSV is one sheet)."""
    import csv

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file is too large (limit is 5 MB).")
    name = (filename or "").lower()
    if name.endswith((".csv", ".txt")):
        text = content.decode("utf-8-sig", "replace")
        return [[[c.strip() for c in row] for row in csv.reader(io.StringIO(text))]]
    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            return [[[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
        except Exception as exc:  # noqa: BLE001 - any parse failure is a bad file
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file could not be read as an Excel workbook.") from exc
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a .csv or .xlsx file.")


def _parse_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for candidate in (text, text[:10]):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _year_for(day: int, month: int, today: date) -> int | None:
    """A header like '1-Oct' has no year: use this year, or last year if that would be far in the future."""
    for year in (today.year, today.year - 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d <= today + timedelta(days=45):
            return year
    return None


def _header_date(raw: object, today: date) -> date | None:
    """A column header that is a date: '1-Oct', '01-Oct-2026', 'Oct 1', '2026-10-01', '1/10', an Excel date ..."""
    text = str(raw or "").strip()
    if not text:
        return None
    full = _parse_date(text)
    if full:
        return full
    m = re.match(r"^(\d{1,2})[\s\-/.]*([A-Za-z]{3,9})\.?(?:[\s\-/.,]*(\d{2,4}))?$", text)
    day = mon = year = None
    if m:
        day, mon, year = int(m.group(1)), _MONTHS.get(m.group(2)[:3].lower()), m.group(3)
    else:
        m = re.match(r"^([A-Za-z]{3,9})\.?[\s\-/.]*(\d{1,2})(?:[\s\-/.,]*(\d{2,4}))?$", text)
        if m:
            mon, day, year = _MONTHS.get(m.group(1)[:3].lower()), int(m.group(2)), m.group(3)
        else:
            m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})$", text)
            if m:
                day, mon, year = int(m.group(1)), int(m.group(2)), None
    if not (day and mon and 1 <= day <= 31 and 1 <= mon <= 12):
        return None
    y = (2000 + int(year) if year and len(year) == 2 else int(year)) if year else _year_for(day, mon, today)
    try:
        return date(y, mon, day) if y else None
    except ValueError:
        return None


@dataclass
class _Layout:
    header_row: int
    code: int | None
    name: int | None
    platform: int | None
    wide_days: list[tuple[int, date]]          # (column, date) when each day is its own column
    date_col: int | None                        # long layout: a date column + a count column
    count_col: int | None


def _find_layout(grid: list[list[str]], today: date) -> _Layout | None:
    """Looks for the header row in the first 25 rows (sheets often have a title or blank rows above it)."""
    for r, row in enumerate(grid[:25]):
        heads = [_norm_header(c) for c in row]

        def find(field_name: str) -> int | None:
            for alias in _ALIASES[field_name]:
                if alias in heads:
                    return heads.index(alias)
            return None

        code, name = find("code"), find("name")
        if code is None and name is None:
            continue
        days = [(i, d) for i, c in enumerate(row) if (d := _header_date(c, today)) is not None]
        date_col, count_col = find("date"), find("count")
        if len(days) >= 1 and not (date_col is not None and count_col is not None and len(days) < 3):
            return _Layout(r, code, name, find("platform"), days, None, None)
        if date_col is not None and count_col is not None:
            return _Layout(r, code, name, find("platform"), [], date_col, count_col)
    return None


def parse_sheet(db: Session, user: User, filename: str, content: bytes) -> Parsed:
    today = date.today()
    layout, grid = None, []
    for g in _grids(filename, content):
        layout = _find_layout(g, today)
        if layout:
            grid = g
            break
    if layout is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Couldn't find the header row. It needs a store column (Outlet ID or Outlet Name) and either one column per "
            "day (like 1-Oct, 2-Oct ...) or a date column plus a filled-bottles column.",
        )

    stores = db.execute(
        select(Store).options(joinedload(Store.region), joinedload(Store.partner_organization))
        .where(Store.organization_id == user.organization_id)
    ).unique().scalars().all()
    by_code: dict[str, list[Store]] = defaultdict(list)
    by_name: dict[str, list[Store]] = defaultdict(list)
    for st in stores:
        by_code[st.external_code.strip().lower()].append(st)
        by_name[" ".join(st.name.lower().split())].append(st)

    def at(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    def to_count(raw: str) -> int | None:
        text = raw.strip().replace(",", "")
        if not text:
            return None
        try:
            n = int(float(text))
        except ValueError:
            return -1
        return n if 0 <= n <= MAX_COUNT else -1

    cards: dict[tuple[uuid.UUID, date], SheetCard] = {}
    unmatched: list[dict] = []
    warnings: list[str] = []
    dup_dates = ignored_cells = rows_read = 0
    seen_months: set[date] = set()

    for n, row in enumerate(grid[layout.header_row + 1:], start=layout.header_row + 2):
        if not any(c.strip() for c in row):
            continue
        code, name_raw = at(row, layout.code), at(row, layout.name)
        if _norm_header(code) in ("total", "grandtotal") or _norm_header(name_raw) in ("total", "grandtotal"):
            continue                                                  # a totals line at the bottom of a sheet
        if not code and not name_raw:
            continue
        rows_read += 1
        label = code or name_raw
        plat = at(row, layout.platform).lower()

        matches = by_code.get(code.lower(), []) if code else []
        if not matches and name_raw:
            matches = by_name.get(" ".join(name_raw.lower().split()), [])
        if plat:
            matches = [m for m in matches if m.partner_organization and m.partner_organization.slug.lower() == plat]
        if not matches:
            unmatched.append({"row": n, "store": label, "reason": "No store with that Outlet ID / name."})
            continue
        if len(matches) > 1:
            unmatched.append({"row": n, "store": label, "reason": "Matches more than one store; add a platform column."})
            continue
        store = matches[0]

        if layout.wide_days:
            cells = [(d, at(row, i)) for i, d in layout.wide_days]
        else:
            d = _parse_date(at(row, layout.date_col))
            if d is None:
                unmatched.append({"row": n, "store": label, "reason": "The date isn't readable."})
                continue
            cells = [(d, at(row, layout.count_col))]
        for d, raw in cells:
            count = to_count(raw)
            if count is None:
                continue                                               # an empty day is not an entry
            if count < 0:
                ignored_cells += 1
                continue
            month = date(d.year, d.month, 1)
            seen_months.add(month)
            card = cards.setdefault((store.id, month), SheetCard(store, month))
            if d in card.entries:
                dup_dates += 1
            card.entries[d] = card.entries.get(d, 0) + count

    if dup_dates:
        warnings.append(f"{dup_dates} store/date value(s) appeared more than once; their counts were added together.")
    if ignored_cells:
        warnings.append(f"{ignored_cells} cell(s) were skipped because they weren't a whole number (text, 'NA', '-' ...).")
    if seen_months:
        warnings.append("Dates read as: " + ", ".join(card_service.month_label(m) for m in sorted(seen_months)) + ".")
    out = sorted(cards.values(), key=lambda c: (c.store.name.lower(), c.month))
    if len(out) > MAX_CARDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"That would be {len(out)} cards; the limit is {MAX_CARDS} per download. Split the sheet.")
    return Parsed(out, unmatched, warnings, rows_read, filename, hashlib.sha256(content).hexdigest())


def preview(db: Session, user: User, p: Parsed) -> dict:
    activity_service.record(
        db, actor=user, action="card_sheet.preview", entity_type="card_sheet", entity_id=p.sha256[:16],
        metadata={"file": p.filename, "rows": p.rows, "cards": len(p.cards), "unmatched": len(p.unmatched)},
    )
    db.commit()
    return {
        "file": p.filename, "rows": p.rows, "cards": len(p.cards), "stores": len({c.store.id for c in p.cards}),
        "entries": sum(len(c.entries) for c in p.cards), "bottles": sum(sum(c.entries.values()) for c in p.cards),
        "unmatched": p.unmatched[:200], "unmatched_count": len(p.unmatched), "warnings": p.warnings,
        "sample": [
            {"store": c.store.name, "code": c.store.external_code, "month": card_service.month_label(c.month), "days": len(c.entries), "bottles": sum(c.entries.values())}
            for c in p.cards[:200]
        ],
    }


# --------------------------------------------------------------------------
# the PDF
# --------------------------------------------------------------------------

def render(db: Session, user: User, p: Parsed) -> tuple[bytes, str]:
    if not p.cards:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No rows in the sheet matched a store, so there is nothing to print.")
    from reportlab.pdfgen import canvas

    contacts = card_service._Contacts(db, user.organization_id)
    stamp = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M UTC")
    footer = f"Source: uploaded sheet '{p.filename[:60]}'. Generated {stamp} by {user.full_name}. Not generated from the order records."
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(card_service.W, card_service.H))
    c.setTitle("Cards from uploaded sheet")
    c.setAuthor(settings.COMPANY_NAME)
    for card in p.cards:
        s = card.store
        platform = (s.partner_organization.name if s.partner_organization else "").upper()
        entries = sorted(card.entries.items())
        card_service._draw_card(c, s, card_service._vendor_key(s), platform, card.month, entries, contacts.for_store(s))
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Oblique", 6.5)
        c.drawCentredString(card_service.W / 2, 9, footer)
        c.showPage()
    c.save()
    activity_service.record(
        db, actor=user, action="card_sheet.download", entity_type="card_sheet", entity_id=p.sha256[:16],
        metadata={"file": p.filename, "sha256": p.sha256, "cards": len(p.cards), "stores": len({x.store.id for x in p.cards}),
                  "entries": sum(len(x.entries) for x in p.cards), "bottles": sum(sum(x.entries.values()) for x in p.cards)},
    )
    db.commit()
    name = card_service._safe_name("Cards_from_sheet", p.filename.rsplit(".", 1)[0][:40]) + ".pdf"
    return buf.getvalue(), name


# --------------------------------------------------------------------------
# random count card (temporary, render-only)
# --------------------------------------------------------------------------

MAX_RANDOM_DAYS = 366


def render_random(db: Session, user: User, store_id: uuid.UUID, rows: list[tuple[date, int]]) -> tuple[bytes, str]:
    """The standard card (one per month) for a store with the rows the caller posted. Render-only: it reads the store
    to draw its details and writes nothing at all (no orders, no audit log, no files), so the numbers exist only in the PDF."""
    if not rows or len(rows) > MAX_RANDOM_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Send between 1 and {MAX_RANDOM_DAYS} dates.")
    days = [d for d, _ in rows]
    if len(set(days)) != len(days):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A date appears more than once.")
    if any(n < 0 or n > MAX_COUNT for _, n in rows):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Counts must be whole numbers of zero or more.")
    store = db.execute(
        select(Store).options(joinedload(Store.region), joinedload(Store.partner_organization))
        .where(Store.id == store_id, Store.organization_id == user.organization_id)
    ).unique().scalar_one_or_none()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")

    from reportlab.pdfgen import canvas

    by_month: dict[date, list[tuple[date, int]]] = defaultdict(list)
    for d, n in sorted(rows):
        by_month[date(d.year, d.month, 1)].append((d, n))
    contacts = card_service._Contacts(db, user.organization_id)
    platform = (store.partner_organization.name if store.partner_organization else "").upper()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(card_service.W, card_service.H))
    c.setTitle("Random count card")
    c.setAuthor(settings.COMPANY_NAME)
    for month, entries in sorted(by_month.items()):
        card_service._draw_card(c, store, card_service._vendor_key(store), platform, month, entries, contacts.for_store(store))
        c.showPage()
    c.save()
    first, last = min(days), max(days)
    code = re.sub(r"[^\w-]+", "_", store.external_code).strip("_") or "store"
    name = f"{code}_Random_Count_Card_{first.isoformat()}_to_{last.isoformat()}.pdf"
    return buf.getvalue(), name
