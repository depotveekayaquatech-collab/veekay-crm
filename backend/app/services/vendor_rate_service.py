"""
Vendor rates: what Veekay (the vendor) charges per bottle, city-wise, optionally overridden for a single store.

An admin uploads a rate sheet:  City | Rate  (a city rate)   and/or   Outlet ID or Store Name | Rate  (a store rate).
  * A rate that is NEW is added straight away.
  * A rate that would CHANGE an existing one is never applied silently: the first upload only returns the list of what
    will change ("these stores are updating"); nothing is written until the admin confirms and uploads again with
    confirm=true.
  * Rates are effective-dated (default: today). The old rows stay as history, so a report for any date uses the rate that
    was in force then.
Lookup order for a store: its own store rate, else its city's rate.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationKind
from app.models.store import Store
from app.models.user import User
from app.models.vendor_rate import VendorRate
from app.services import activity_service
from app.services.store_sync_service import SyncError, rows_from_upload

MAX_RATE = Decimal("100000")
_CITY = ("city",)
_RATE = ("rate", "vendor rate", "rate per bottle", "vendor_rate", "rate (per bottle)")
_CODE = ("outlet id", "outlet_id", "store id", "store code")
_NAME = ("store name", "outlet name", "store")
MAX_LISTED = 300
EPOCH = date(2000, 1, 1)   # a store's or city's FIRST rate applies from the beginning, so older reports show it too


def _today() -> date:
    return datetime.now(timezone.utc).date()


def city_key(city: str | None) -> str:
    return " ".join((city or "").lower().split())


def _partner(db: Session, slug: str) -> Organization:
    p = db.execute(select(Organization).where(Organization.slug == slug.strip().lower(), Organization.kind == OrganizationKind.PARTNER.value)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{slug}' is not a platform in the CRM.")
    return p


def _rate(raw: str) -> Decimal | None:
    text = (raw or "").strip().replace(",", "").replace("₹", "").replace("Rs.", "").strip()
    if not text:
        return None
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise ValueError("not a number") from None
    if not d.is_finite() or d < 0 or d > MAX_RATE:
        raise ValueError("out of range")
    return d.quantize(Decimal("0.01"))


# ------------------------------------------------------------------ lookup (used by the reports)

class RateBook:
    """All rates of the given platforms in force on `on_date`, looked up without a query per store."""

    def __init__(self, db: Session, partner_ids: list[uuid.UUID], on_date: date):
        self._city: dict[tuple[uuid.UUID, str], Decimal] = {}
        self._store: dict[uuid.UUID, Decimal] = {}
        if not partner_ids:
            return
        rows = db.execute(
            select(VendorRate).where(VendorRate.partner_organization_id.in_(partner_ids), VendorRate.effective_from <= on_date)
            .order_by(VendorRate.effective_from, VendorRate.created_at)
        ).scalars()
        for r in rows:   # later rows overwrite earlier ones: the newest rate in force wins
            if r.store_id is not None:
                self._store[r.store_id] = r.rate
            else:
                self._city[(r.partner_organization_id, r.city_key)] = r.rate

    def for_store(self, store: Store) -> Decimal | None:
        if store.id in self._store:            # a store's own rate beats its city's (and a 0.00 rate is a real rate)
            return self._store[store.id]
        return self._city.get((store.partner_organization_id, city_key(store.city)))


def current_rates(db: Session, slug: str, on_date: date | None = None) -> list[dict]:
    partner = _partner(db, slug)
    on = on_date or _today()
    rows = db.execute(
        select(VendorRate).where(VendorRate.partner_organization_id == partner.id, VendorRate.effective_from <= on)
        .order_by(VendorRate.effective_from, VendorRate.created_at)
    ).scalars().all()
    latest: dict[tuple, VendorRate] = {}
    for r in rows:
        latest[(r.city_key, r.store_id)] = r
    names = {s.id: (s.name, s.external_code) for s in db.execute(select(Store).where(Store.id.in_([r.store_id for r in latest.values() if r.store_id] or [uuid.uuid4()]))).scalars()}
    out = [
        {"scope": "store" if r.store_id else "city", "city": r.city,
         "store_name": names[r.store_id][0] if r.store_id in names else None,
         "outlet_id": names[r.store_id][1] if r.store_id in names else None,
         "rate": r.rate, "effective_from": r.effective_from}
        for r in latest.values()
    ]
    out.sort(key=lambda x: (x["scope"] != "city", city_key(x["city"]), x["store_name"] or ""))
    return out


# ------------------------------------------------------------------ upload

def upload(
    db: Session, actor: User, slug: str, filename: str, content: bytes, *, confirm: bool, effective_from: date | None,
) -> dict:
    partner = _partner(db, slug)
    eff = effective_from or _today()
    try:
        rows = rows_from_upload(filename, content)
    except SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The rate sheet has no rows.")
    keys = {k.strip().lower(): k for k in rows[0]}
    pick = lambda names: next((keys[n] for n in names if n in keys), None)  # noqa: E731
    c_city, c_rate, c_code, c_name = pick(_CITY), pick(_RATE), pick(_CODE), pick(_NAME)
    if c_rate is None or (c_city is None and c_code is None and c_name is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet needs a 'Rate' column and a 'City' column (and/or 'Outlet ID' or 'Store Name' for store-specific rates).")

    stores = list(db.execute(select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)).scalars())
    by_code = {s.external_code: s for s in stores}
    by_name: dict[str, list[Store]] = defaultdict(list)
    for s in stores:
        by_name[s.name.strip().lower()].append(s)
    book = RateBook(db, [partner.id], eff)
    stores_in_city: dict[str, list[Store]] = defaultdict(list)
    for s in stores:
        stores_in_city[city_key(s.city)].append(s)

    targets: dict[tuple[str, uuid.UUID | None], dict] = {}
    warnings: list[str] = []
    bad = unknown = 0
    for i, row in enumerate(rows, start=2):
        code, name, city = (row.get(c_code) or "").strip() if c_code else "", (row.get(c_name) or "").strip() if c_name else "", (row.get(c_city) or "").strip() if c_city else ""
        if not (code or name or city) and not (row.get(c_rate) or "").strip():
            continue
        try:
            rate = _rate(row.get(c_rate) or "")
        except ValueError:
            bad += 1
            continue
        if rate is None:
            continue
        store = None
        if code or name:
            store = by_code.get(code) if code else None
            if store is None and name:
                hits = by_name.get(name.lower(), [])
                if len(hits) == 1:
                    store = hits[0]
                elif len(hits) > 1:
                    warnings.append(f"Row {i}: '{name}' matches {len(hits)} stores; use the Outlet ID. Skipped.")
                    continue
            if store is None:
                unknown += 1
                continue
            targets[("store", store.id)] = {"store": store, "city": store.city or city, "rate": rate}
        else:
            if not city:
                bad += 1
                continue
            targets[("city", city_key(city))] = {"store": None, "city": city, "rate": rate}   # last row for a city wins

    new, changes, unchanged = [], [], 0
    for (scope, key), t in targets.items():
        store = t["store"]
        old = book._store.get(store.id) if store is not None else book._city.get((partner.id, key))  # noqa: SLF001
        item = {"scope": scope, "city": t["city"], "store_name": store.name if store else None, "outlet_id": store.external_code if store else None, "old_rate": old, "new_rate": t["rate"]}
        if old is None:
            new.append(item)
        elif old == t["rate"]:
            unchanged += 1
        else:
            if scope == "city":   # a city rate reaches every store of that city that has no rate of its own
                item["stores_affected"] = sum(1 for s in stores_in_city.get(key, []) if s.id not in book._store)  # noqa: SLF001
            changes.append(item)

    if bad:
        warnings.append(f"{bad} row(s) skipped: the rate is not a number from 0 to {MAX_RATE:,} or there is no city.")
    if unknown:
        warnings.append(f"{unknown} store(s) in the sheet were not found on {partner.name} and were skipped.")

    result = {
        "applied": False, "needs_confirmation": False, "effective_from": eff, "new": len(new), "changed": len(changes), "unchanged": unchanged,
        "changes": changes[:MAX_LISTED], "new_rates": new[:MAX_LISTED], "warnings": warnings,
        "stores_affected": sum(c.get("stores_affected", 1) for c in changes),
    }
    if changes and not confirm:
        result["needs_confirmation"] = True      # nothing has been written
        return result
    if not new and not changes:
        return result

    existing_rows = {(r.city_key, r.store_id, r.effective_from): r for r in db.execute(
        select(VendorRate).where(VendorRate.partner_organization_id == partner.id, VendorRate.effective_from.in_([eff, EPOCH]))).scalars()}
    for (scope, key), t in targets.items():
        store = t["store"]
        old = book._store.get(store.id) if store is not None else book._city.get((partner.id, key))  # noqa: SLF001
        if old == t["rate"]:
            continue
        ckey = city_key(t["city"]) if store is not None else key
        row_eff = EPOCH if (old is None and effective_from is None) else eff   # first-ever rate: from the beginning
        same = existing_rows.get((ckey, store.id if store else None, row_eff))
        if same is not None:
            same.rate, same.uploaded_by_user_id = t["rate"], actor.id
        else:
            db.add(VendorRate(partner_organization_id=partner.id, city_key=ckey, city=(t["city"] or "")[:64], store_id=store.id if store else None,
                              rate=t["rate"], effective_from=row_eff, uploaded_by_user_id=actor.id))
    activity_service.record(
        db, actor=actor, action="vendor_rates.uploaded", entity_type="vendor_rate", entity_id=partner.id,
        metadata={"platform": partner.slug, "new": len(new), "changed": len(changes), "effective_from": eff.isoformat(), "confirmed": confirm},
    )
    db.commit()
    result["applied"] = True
    return result
