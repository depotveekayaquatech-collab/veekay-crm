"""
Random count cards for a whole sheet: one store and one total per row (no dates), a date range chosen on the page, and one
PDF of standard cards. The tools around the single-store random generator in card_sheet_service.

Reading the sheet is the only server-side step that needs the CRM (to match each row to a store); the random split itself is
made on the page and sent back for drawing, so, like the single-store version, nothing is stored or logged.
"""
from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.store import Store
from app.models.user import User
from app.services import card_service
from app.services.card_sheet_service import (
    MAX_COUNT, MAX_RANDOM_DAYS, _alnum, _content_store_col, _grids,
)

MAX_BULK_STORES = 400
_COUNT_HEADS = ("totalcount", "total", "count", "bottles", "filledbottles", "qty", "quantity", "delivered", "sum")
_NOT_A_STORE = ("total", "grandtotal", "outletname", "storename", "outletid", "name", "store", "outlet")


def _as_total(raw: str) -> int | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        n = float(text)
    except ValueError:
        return None
    return int(n) if n.is_integer() and 0 <= n <= MAX_COUNT else None


def _suggestions(name_key: str, by_key: dict[str, list[Store]], limit: int = 4) -> list[dict]:
    """Stores whose name is close to one that matched nothing (a sheet and the CRM often differ by a suffix or a spelling)."""
    scored: dict[uuid.UUID, tuple[float, Store]] = {}
    for key, stores in by_key.items():
        if not key or not name_key:
            continue
        ratio = SequenceMatcher(None, name_key, key).ratio()
        if key.startswith(name_key) or name_key.startswith(key) or name_key in key:
            ratio = max(ratio, 0.9)
        if ratio >= 0.72:
            for st in stores:
                if st.id not in scored or scored[st.id][0] < ratio:
                    scored[st.id] = (ratio, st)
    best = sorted(scored.values(), key=lambda t: (-t[0], t[1].name))[:limit]
    return [{"store_id": st.id, "name": st.name, "code": st.external_code} for _, st in best]


def parse_totals(db: Session, user: User, filename: str, content: bytes) -> dict:
    """Reads a sheet of one store and one total per row, with or without a header row, with the store written however the
    sheet writes it (Outlet ID, Outlet Name, anything the CRM knows). Returns what matched and what didn't, with
    suggestions for the rest, so the person can fix those before any card is drawn."""
    stores = db.execute(
        select(Store).options(joinedload(Store.partner_organization)).where(Store.organization_id == user.organization_id)
    ).unique().scalars().all()
    by_key: dict[str, list[Store]] = defaultdict(list)
    for st in stores:
        for k in {_alnum(st.external_code), _alnum(st.name)}:
            if k:
                by_key[k].append(st)
    known = set(by_key)

    grids = _grids(filename, content)
    best_grid, best_hits, best_col = None, 0, None
    for g in grids:
        col = _content_store_col(g, -1, set(), known)
        if col is None:
            continue
        hits = sum(1 for row in g if col < len(row) and _alnum(row[col]) in known)
        if hits > best_hits:
            best_grid, best_hits, best_col = g, hits, col
    if best_grid is None:                           # nothing recognisable: use the column that looks most like names
        for g in grids:
            width = max((len(r) for r in g), default=0)
            for i in range(width):
                texty = sum(1 for r in g if i < len(r) and len(r[i].strip()) >= 3 and _as_total(r[i]) is None)
                if texty > best_hits:
                    best_grid, best_hits, best_col = g, texty, i
    if best_grid is None or best_col is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't find a column of store names or Outlet IDs in that file.")

    width = max(len(r) for r in best_grid)
    candidates = []
    for i in range(width):
        if i == best_col:
            continue
        numbers = sum(1 for r in best_grid if i < len(r) and _as_total(r[i]) is not None)
        headed = any(_alnum(r[i]) in _COUNT_HEADS for r in best_grid[:6] if i < len(r))
        candidates.append((headed, numbers, i))
    if not candidates or max(c[1] for c in candidates) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't find a column of counts next to the store names.")
    count_col = max(candidates)[2]                   # a column headed Total / Count wins, otherwise the one with most numbers

    matched: dict[uuid.UUID, dict] = {}
    unmatched: list[dict] = []
    rows = repeated = without_count = 0
    for n, row in enumerate(best_grid, start=1):
        name = row[best_col].strip() if best_col < len(row) else ""
        if not name or _alnum(name) in _NOT_A_STORE:
            continue
        total = _as_total(row[count_col]) if count_col < len(row) else None
        if total is None:
            without_count += 1                       # a header row, a title, or a store without a number
            continue
        rows += 1
        found = by_key.get(_alnum(name), [])
        if len(found) == 1:
            st = found[0]
            if st.id in matched:
                matched[st.id]["total"] += total
                repeated += 1
            else:
                matched[st.id] = {
                    "row": n, "sheet_name": name, "store_id": st.id, "store_name": st.name, "code": st.external_code,
                    "platform": st.partner_organization.slug if st.partner_organization else None, "total": total,
                }
        else:
            unmatched.append({
                "row": n, "name": name, "total": total,
                "reason": "More than one store has this name." if found else "No store with that name or Outlet ID.",
                "suggestions": [{"store_id": s.id, "name": s.name, "code": s.external_code} for s in found[:4]] if found else _suggestions(_alnum(name), by_key),
            })
    warnings = [f"{repeated} store(s) appeared more than once in the sheet; their totals were added together."] if repeated else []
    if len(matched) + len(unmatched) > MAX_BULK_STORES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"That sheet has {len(matched) + len(unmatched)} stores; the limit is {MAX_BULK_STORES} per PDF. Split it.",
        )
    return {"file": filename, "rows": rows, "matched": list(matched.values()), "unmatched": unmatched, "warnings": warnings}


def render_bulk(db: Session, user: User, items: list[tuple[uuid.UUID, list[tuple[date, int]]]]) -> tuple[bytes, str]:
    """One PDF of standard cards, in the order given, from the daily counts the page generated for many stores.
    Render-only: nothing is stored or logged."""
    if not items or len(items) > MAX_BULK_STORES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Send between 1 and {MAX_BULK_STORES} stores.")
    ids = [sid for sid, _ in items]
    if len(set(ids)) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A store appears more than once.")
    all_days: list[date] = []
    for _, rows in items:
        days = [d for d, _ in rows]
        if not rows or len(rows) > MAX_RANDOM_DAYS or len(set(days)) != len(days):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Each store needs 1 to {MAX_RANDOM_DAYS} different dates.")
        if any(n < 0 or n > MAX_COUNT for _, n in rows):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Counts must be whole numbers of zero or more.")
        all_days += days
    stores = {
        s.id: s for s in db.execute(
            select(Store).options(joinedload(Store.region), joinedload(Store.partner_organization))
            .where(Store.id.in_(ids), Store.organization_id == user.organization_id)
        ).unique().scalars().all()
    }
    if len(stores) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One of the stores was not found.")

    from reportlab.pdfgen import canvas

    contacts = card_service._Contacts(db, user.organization_id)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(card_service.W, card_service.H))
    c.setTitle("Random count cards")
    c.setAuthor(settings.COMPANY_NAME)
    for sid, rows in items:
        store = stores[sid]
        platform = (store.partner_organization.name if store.partner_organization else "").upper()
        by_month: dict[date, list[tuple[date, int]]] = defaultdict(list)
        for d, n in sorted(rows):
            by_month[date(d.year, d.month, 1)].append((d, n))
        for month, entries in sorted(by_month.items()):
            card_service._draw_card(c, store, card_service._vendor_key(store), platform, month, entries, contacts.for_store(store))
            c.showPage()
    c.save()
    return buf.getvalue(), f"Random_Count_Cards_{min(all_days).isoformat()}_to_{max(all_days).isoformat()}.pdf"
