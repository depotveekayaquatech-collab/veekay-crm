"""
Bulk-mark orders from an uploaded order sheet.

Expected layout ("wide"): one row per store, one column per date.

    Outlet ID | Outlet Name | ... | 2026-09-01 | 2026-09-02 | ...
    5285      | SS Gurgaon  | ... | 31         | 24         | ...

  - A blank cell means "not marked" (no entry is written).
  - 0 is a real value ("marked, zero bottles") and is imported.
  - Extra columns (S.No, Entity, POC, vendor, "total", ...) are ignored.
  - In an Excel workbook every tab that has an Outlet ID column and at least
    one date column is imported; other tabs (employees, logs, ...) are skipped
    and never read beyond their header row.

Rules follow the normal order rules: counts 0..MAX_BOTTLE_COUNT, no future
dates, one entry per (store, date). Imported rows are recorded as ADMIN
entries. Existing entries are kept unless `overwrite` is set.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store
from app.models.user import User
from app.services import activity_service

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_ID_HEADERS = ("outlet id", "outlet_id", "store id", "store code", "outlet code", "id")


class OrderImportError(Exception):
    """Whole-file failure (bad type, no usable sheet, unknown platform)."""


@dataclass
class OrderImportResult:
    platform: str
    sheets: list[str] = field(default_factory=list)
    rows_read: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    kept_existing: int = 0      # entry already there with a different value, overwrite off
    unknown_stores: int = 0     # distinct Outlet IDs not found on this platform
    invalid_values: int = 0
    future_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {**self.__dict__, "warnings": self.warnings[:50]}


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _header_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt, size in (("%Y-%m-%d", 10), ("%d-%m-%Y", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def _id_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _count(value: object) -> tuple[int | None, bool]:
    """(count, is_invalid). Blank -> (None, False) = not marked."""
    if value is None:
        return None, False
    if isinstance(value, bool):
        return None, True
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return None, True
        n = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None, False
        try:
            n = int(float(text))
        except ValueError:
            return None, True
    if not (settings.MIN_BOTTLE_COUNT <= n <= settings.MAX_BOTTLE_COUNT):
        return None, True
    return n, False


def _grids(filename: str, content: bytes) -> list[tuple[str, list[tuple]]]:
    """[(sheet_name, rows)] — rows are tuples of raw cell values."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise OrderImportError("That file is too large (limit is 10 MB).")
    name = (filename or "").lower()
    if name.endswith((".csv", ".txt")):
        text = content.decode("utf-8-sig", "replace")
        return [("CSV", [tuple(r) for r in csv.reader(io.StringIO(text))])]
    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover
            raise OrderImportError("Excel files need the 'openpyxl' package on the server.") from exc
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise OrderImportError("That file could not be read as an Excel workbook.") from exc
        return [(ws.title, list(ws.iter_rows(values_only=True))) for ws in wb.worksheets]
    raise OrderImportError("Upload a .csv or .xlsx file.")


def _locate(rows: list[tuple]) -> tuple[int, int, dict[int, date]] | None:
    """Find (header_row_index, id_column, {column_index: date}) or None."""
    for r_idx, row in enumerate(rows[:5]):
        id_col = next(
            (i for i, c in enumerate(row) if isinstance(c, str) and c.strip().lower() in _ID_HEADERS),
            None,
        )
        if id_col is None:
            continue
        date_cols = {i: d for i, c in enumerate(row) if (d := _header_date(c)) is not None}
        if date_cols:
            return r_idx, id_col, date_cols
    return None


# --------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------

def import_orders(
    db: Session, actor: User, partner_slug: str, filename: str, content: bytes, *, overwrite: bool = False
) -> OrderImportResult:
    partner_slug = partner_slug.strip().lower()
    partner = db.execute(
        select(Organization).where(
            Organization.slug == partner_slug, Organization.kind == OrganizationKind.PARTNER.value
        )
    ).scalar_one_or_none()
    if partner is None:
        raise OrderImportError(f"'{partner_slug}' is not a configured platform in the CRM.")

    result = OrderImportResult(platform=partner_slug)

    # {(outlet_code, date): count}; later sheets override earlier ones for the same cell.
    wanted: dict[tuple[str, date], int] = {}
    for sheet_name, rows in _grids(filename, content):
        found = _locate(rows)
        if found is None:
            continue
        header_idx, id_col, date_cols = found
        rows_before = result.rows_read
        for row in rows[header_idx + 1:]:
            code = _id_text(row[id_col]) if id_col < len(row) else ""
            if not code:
                continue
            result.rows_read += 1
            for col, d in date_cols.items():
                raw = row[col] if col < len(row) else None
                n, bad = _count(raw)
                if bad:
                    result.invalid_values += 1
                elif n is not None:
                    wanted[(code, d)] = n
        if result.rows_read > rows_before:
            result.sheets.append(sheet_name)

    if not wanted and not result.invalid_values:
        raise OrderImportError(
            "No order data found. Each sheet needs an 'Outlet ID' column and date columns such as 2026-09-01."
        )

    stores = {
        s.external_code: s
        for s in db.execute(
            select(Store).where(
                Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id
            )
        ).scalars()
    }

    unknown = {code for code, _ in wanted if code not in stores}
    result.unknown_stores = len(unknown)
    wanted = {k: v for k, v in wanted.items() if k[0] in stores}

    if wanted:
        dates = [d for _, d in wanted]
        existing = {
            (e.store_id, e.order_date): e
            for e in db.execute(
                select(OrderEntry).where(
                    OrderEntry.store_id.in_({stores[c].id for c, _ in wanted}),
                    OrderEntry.order_date >= min(dates),
                    OrderEntry.order_date <= max(dates),
                )
            ).scalars()
        }
        today = _today()
        for (code, d), n in wanted.items():
            if d > today:
                result.future_skipped += 1
                continue
            store = stores[code]
            entry = existing.get((store.id, d))
            if entry is None:
                db.add(OrderEntry(
                    organization_id=actor.organization_id, store_id=store.id, order_date=d,
                    bottle_count=n, source=EntrySource.ADMIN.value, marked_by_user_id=actor.id,
                ))
                result.created += 1
            elif entry.bottle_count == n:
                result.unchanged += 1
            elif overwrite:
                entry.bottle_count = n
                entry.source = EntrySource.ADMIN.value
                entry.marked_by_user_id = actor.id
                result.updated += 1
            else:
                result.kept_existing += 1

    if unknown:
        sample = ", ".join(sorted(unknown)[:8])
        result.warnings.append(
            f"{len(unknown)} Outlet ID{'s' if len(unknown) > 1 else ''} not found on {partner.name} "
            f"and skipped (e.g. {sample}). Import the stores first."
        )
    if result.invalid_values:
        result.warnings.append(
            f"{result.invalid_values} cell{'s' if result.invalid_values > 1 else ''} skipped: not a whole number "
            f"from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}."
        )
    if result.future_skipped:
        result.warnings.append(f"{result.future_skipped} future-dated cells were skipped.")
    if result.kept_existing:
        result.warnings.append(
            f"{result.kept_existing} existing entries had a different value and were kept "
            "(turn on 'Overwrite existing entries' to replace them)."
        )

    activity_service.record(
        db, actor=actor, action="order.imported", entity_type="order_entry", entity_id=partner.id,
        metadata={
            "platform": partner_slug, "sheets": result.sheets, "created": result.created,
            "updated": result.updated, "overwrite": overwrite,
        },
    )
    db.commit()
    return result
