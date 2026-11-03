"""
Takes rows from Busy 21 (the secured API call, or an admin's CSV upload) into the vendor ledger. One routine serves both, so they behave identically.

  * every row is validated; bad rows are listed with a clear reason and the good ones are still processed
  * a row is matched to a CRM vendor by vendor_code ONLY (given, or taken from the end of account_name); never by name
  * a row whose code is not a CRM vendor is parked in busy_unmatched_entries with its raw row, never dropped
  * the ledger key is (vendor_code, voucher_no, entry_type): sending the same data again changes nothing, an edited entry is updated in place
  * mode "replace_period" also removes API-sourced entries in the period that Busy no longer has, so edits and deletions in Busy carry over;
    all inside one transaction (the final state is the same as delete-then-insert, but the counts stay honest)
  * a dry run does all of it and rolls back, so the preview's numbers are exactly what the real run will do
"""
import hashlib
import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.busy_ledger import (
    ENTRY_TYPES, STATUS_FAILED, STATUS_PARTIAL, STATUS_SUCCESS, BusyLedgerEntry, BusySyncLog, BusyUnmatchedEntry, BusyVendor, BusyVendorAlias,
)
from app.services.busy_codes import MAX_CODE_LENGTH, extract_vendor_code, normalize_code

log = logging.getLogger("busy_sync")

MODE_UPSERT, MODE_REPLACE = "upsert", "replace_period"
CHUNK = 1000
MAX_ERRORS_RETURNED = 200
MAX_UNMATCHED_CODES_RETURNED = 20
MAX_AMOUNT = Decimal("999999999999.99")          # NUMERIC(14,2)
MAX_VOUCHER_LENGTH = 64
MAX_NARRATION_LENGTH = 1000
MAX_ACCOUNT_NAME_LENGTH = 300
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class ValidRow:
    index: int                      # 1-based position in the request, for error messages
    vendor_code: str | None
    account_name: str
    entry_date: date
    entry_type: str
    amount: Decimal
    voucher_no: str
    narration: str | None
    raw: dict[str, Any]


@dataclass
class SyncOutcome:
    received: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    unmatched: int = 0
    rejected: int = 0
    status: str = STATUS_SUCCESS
    errors: list[dict[str, Any]] = field(default_factory=list)
    unmatched_codes: list[str] = field(default_factory=list)
    sample: list[dict[str, Any]] = field(default_factory=list)
    dry_run: bool = False
    log_id: uuid.UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "dry_run": self.dry_run, "log_id": str(self.log_id) if self.log_id else None,
            "received": self.received, "inserted": self.inserted, "updated": self.updated, "unchanged": self.unchanged,
            "deleted": self.deleted, "unmatched": self.unmatched, "rejected": self.rejected,
            "errors": self.errors[:MAX_ERRORS_RETURNED], "errors_truncated": len(self.errors) > MAX_ERRORS_RETURNED,
            "unmatched_codes": self.unmatched_codes, "sample": self.sample,
        }


# ---- row parsing -----------------------------------------------------------

def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip() if value is not None else ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("date must be YYYY-MM-DD (DD/MM/YYYY and DD-MM-YYYY are also accepted)")


def parse_amount(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("amount is required")
    text = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("amount must be a number") from exc
    if not amount.is_finite():
        raise ValueError("amount must be a number")
    if amount <= 0:
        raise ValueError("amount must be greater than zero (use type BILL or PAYMENT for the direction)")
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        raise ValueError("amount can have at most 2 decimal places")
    if amount > MAX_AMOUNT:
        raise ValueError("amount is too large")
    return amount.quantize(_CENT)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def validate_row(index: int, raw: Any) -> ValidRow | str:
    """A ValidRow, or a one-line reason why the row is rejected (every problem in the row is listed)."""
    if not isinstance(raw, dict):
        return "each entry must be an object"
    problems: list[str] = []

    entry_type = _text(raw.get("type")).upper()
    if entry_type not in ENTRY_TYPES:
        problems.append("type must be BILL or PAYMENT")
    voucher_no = _text(raw.get("voucher_no"))
    if not voucher_no:
        problems.append("voucher_no is required")
    elif len(voucher_no) > MAX_VOUCHER_LENGTH:
        problems.append(f"voucher_no is longer than {MAX_VOUCHER_LENGTH} characters")
    entry_date = amount = None
    try:
        entry_date = parse_date(raw.get("date"))
    except ValueError as exc:
        problems.append(str(exc))
    try:
        amount = parse_amount(raw.get("amount"))
    except ValueError as exc:
        problems.append(str(exc))

    account_name = " ".join(_text(raw.get("account_name")).split())[:MAX_ACCOUNT_NAME_LENGTH]
    code = normalize_code(raw.get("vendor_code")) or None
    if code and len(code) > MAX_CODE_LENGTH:
        problems.append(f"vendor_code is longer than {MAX_CODE_LENGTH} characters")
    if not code:
        code = extract_vendor_code(account_name)
        if not account_name:
            problems.append("vendor_code or account_name is required")

    if problems or entry_date is None or amount is None:
        return "; ".join(problems)
    narration = _text(raw.get("narration"))[:MAX_NARRATION_LENGTH] or None
    return ValidRow(index, code, account_name, entry_date, entry_type, amount, voucher_no, narration, raw)


# ---- matching ---------------------------------------------------------------

def resolve_codes(db: Session, codes: set[str]) -> dict[str, str]:
    """{code as sent: the CRM vendor's own code} for every code that is a vendor, or an alias an admin set for one. Codes not in the result are unmatched."""
    if not codes:
        return {}
    found = {c: c for c in db.scalars(select(BusyVendor.vendor_code).where(BusyVendor.vendor_code.in_(codes)))}
    rest = codes - found.keys()
    if rest:
        found.update(db.execute(select(BusyVendorAlias.alias_code, BusyVendorAlias.vendor_code).where(BusyVendorAlias.alias_code.in_(rest))).all())
    return found


def unmatched_key(row: ValidRow) -> str:
    text = f"{row.vendor_code or ''}|{row.account_name.lower()}|{row.voucher_no}|{row.entry_type}"
    return hashlib.sha1(text.encode()).hexdigest()  # noqa: S324 - an identity key, not a secret


# ---- writing ----------------------------------------------------------------

def upsert_ledger(db: Session, rows: list[ValidRow], source: str, now: datetime) -> tuple[int, int]:
    """(inserted, updated) for rows whose vendor_code is already the CRM vendor's own. Rows identical to what is stored are touched not at all."""
    inserted = updated = 0
    for start in range(0, len(rows), CHUNK):
        values = [
            {"id": uuid.uuid4(), "vendor_code": r.vendor_code, "entry_date": r.entry_date, "entry_type": r.entry_type, "amount": r.amount,
             "voucher_no": r.voucher_no, "narration": r.narration, "source": source, "synced_at": now, "created_at": now, "updated_at": now}
            for r in rows[start:start + CHUNK]
        ]
        stmt = pg_insert(BusyLedgerEntry).values(values)
        new = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            constraint="uq_busy_ledger_key",
            set_={"entry_date": new.entry_date, "amount": new.amount, "narration": new.narration, "source": new.source, "synced_at": new.synced_at, "updated_at": new.updated_at},
            where=or_(
                BusyLedgerEntry.entry_date.is_distinct_from(new.entry_date), BusyLedgerEntry.amount.is_distinct_from(new.amount),
                BusyLedgerEntry.narration.is_distinct_from(new.narration), BusyLedgerEntry.source.is_distinct_from(new.source),
            ),
        ).returning(literal_column("(xmax = 0)"))
        for (was_inserted,) in db.execute(stmt).all():
            inserted += bool(was_inserted)
            updated += not was_inserted
    return inserted, updated


def _upsert_unmatched(db: Session, rows: list[ValidRow], source: str, log_id: uuid.UUID | None, now: datetime) -> None:
    for start in range(0, len(rows), CHUNK):
        values = [
            {"id": uuid.uuid4(), "dedupe_key": unmatched_key(r), "vendor_code": r.vendor_code, "account_name": r.account_name, "entry_date": r.entry_date,
             "entry_type": r.entry_type, "amount": r.amount, "voucher_no": r.voucher_no, "narration": r.narration, "source": source, "raw": r.raw,
             "sync_log_id": log_id, "status": "OPEN", "created_at": now, "updated_at": now}
            for r in rows[start:start + CHUNK]
        ]
        stmt = pg_insert(BusyUnmatchedEntry).values(values)
        new = stmt.excluded
        db.execute(stmt.on_conflict_do_update(
            constraint="uq_busy_unmatched_dedupe",
            set_={"entry_date": new.entry_date, "amount": new.amount, "narration": new.narration, "raw": new.raw, "source": new.source,
                  "sync_log_id": new.sync_log_id, "updated_at": new.updated_at},
        ))


def _delete_stale_api_rows(db: Session, vendor_codes: set[str], start: date, end: date, keep: set[tuple[str, str, str]]) -> int:
    existing = db.execute(
        select(BusyLedgerEntry.id, BusyLedgerEntry.vendor_code, BusyLedgerEntry.voucher_no, BusyLedgerEntry.entry_type).where(
            BusyLedgerEntry.source == "API", BusyLedgerEntry.vendor_code.in_(vendor_codes), BusyLedgerEntry.entry_date.between(start, end))
    ).all()
    stale = [row.id for row in existing if (row.vendor_code, row.voucher_no, row.entry_type) not in keep]
    for i in range(0, len(stale), CHUNK):
        db.execute(delete(BusyLedgerEntry).where(BusyLedgerEntry.id.in_(stale[i:i + CHUNK])))
    return len(stale)


def _apply(db: Session, *, entries: list[Any], mode: str, period: tuple[date, date] | None, vendor_codes: list[str], source: str,
           log_id: uuid.UUID | None, now: datetime) -> SyncOutcome:
    out = SyncOutcome(received=len(entries))
    valid: list[ValidRow] = []
    for i, raw in enumerate(entries, start=1):
        row = validate_row(i, raw)
        if isinstance(row, str):
            out.errors.append({"row": i, "message": row, "voucher_no": _text(raw.get("voucher_no")) if isinstance(raw, dict) else ""})
        elif mode == MODE_REPLACE and period and not period[0] <= row.entry_date <= period[1]:
            out.errors.append({"row": i, "message": f"date {row.entry_date} is outside the period {period[0]} to {period[1]}", "voucher_no": row.voucher_no})
        else:
            valid.append(row)

    canon = resolve_codes(db, {r.vendor_code for r in valid if r.vendor_code})
    matched: list[ValidRow] = []
    unmatched: list[ValidRow] = []
    seen: set[tuple[str, ...]] = set()
    for r in valid:
        code = canon.get(r.vendor_code) if r.vendor_code else None
        key = (code, r.voucher_no, r.entry_type) if code else ("?", unmatched_key(r))
        if key in seen:
            out.errors.append({"row": r.index, "message": "duplicate of an earlier row in this request (same vendor_code, voucher_no and type)", "voucher_no": r.voucher_no})
            continue
        seen.add(key)
        (matched if code else unmatched).append(replace(r, vendor_code=code) if code else r)
    out.errors.sort(key=lambda e: e["row"])
    out.rejected = len(out.errors)
    out.unmatched = len(unmatched)
    out.unmatched_codes = sorted({r.vendor_code or "(no code)" for r in unmatched})[:MAX_UNMATCHED_CODES_RETURNED]

    out.inserted, out.updated = upsert_ledger(db, matched, source, now)
    out.unchanged = len(matched) - out.inserted - out.updated
    if mode == MODE_REPLACE and period and (valid or not entries):          # a request whose every row was rejected deletes nothing
        targets = {r.vendor_code for r in matched} | set(resolve_codes(db, {normalize_code(c) for c in vendor_codes if normalize_code(c)}).values())
        if targets:
            out.deleted = _delete_stale_api_rows(db, targets, period[0], period[1], {(r.vendor_code, r.voucher_no, r.entry_type) for r in matched})
    _upsert_unmatched(db, unmatched, source, log_id, now)
    out.sample = [{"row": r.index, "vendor_code": r.vendor_code, "date": r.entry_date.isoformat(), "type": r.entry_type, "amount": str(r.amount),
                   "voucher_no": r.voucher_no} for r in (matched + unmatched)[:10]]
    return out


def _status_for(out: SyncOutcome) -> tuple[str, str | None]:
    first = f"row {out.errors[0]['row']}: {out.errors[0]['message']}" if out.errors else ""
    if out.received and out.rejected == out.received:
        return STATUS_FAILED, f"All {out.received} row(s) were rejected. First problem: {first}"
    if out.rejected:
        return STATUS_PARTIAL, f"{out.rejected} row(s) rejected. First problem: {first}"
    return STATUS_SUCCESS, None


def run_sync(db: Session, *, entries: list[Any], mode: str = MODE_UPSERT, period: tuple[date, date] | None = None, vendor_codes: list[str] | None = None,
             source: str, triggered_by: str | None, dry_run: bool = False) -> SyncOutcome:
    """Apply one batch. Real runs commit the data and their SyncLog row together (a failure rolls the data back and still logs FAILED, then raises).
    Dry runs write nothing at all."""
    started = datetime.now(timezone.utc)
    sync_log: BusySyncLog | None = None
    try:
        if not dry_run:
            sync_log = BusySyncLog(started_at=started, source=source, mode=mode, period_from=period[0] if period else None, period_to=period[1] if period else None,
                                   triggered_by=(triggered_by or "")[:120] or None, status=STATUS_FAILED)
            db.add(sync_log)
            db.flush()
        out = _apply(db, entries=entries, mode=mode, period=period, vendor_codes=vendor_codes or [], source=source,
                     log_id=sync_log.id if sync_log else None, now=started)
        out.dry_run = dry_run
        out.status, message = _status_for(out)
        if dry_run:
            db.rollback()
            return out
        assert sync_log is not None
        sync_log.finished_at = datetime.now(timezone.utc)
        sync_log.status, sync_log.error_message = out.status, message
        sync_log.rows_received, sync_log.rows_inserted, sync_log.rows_updated = out.received, out.inserted, out.updated
        sync_log.rows_unchanged, sync_log.rows_deleted, sync_log.rows_unmatched, sync_log.rows_rejected = out.unchanged, out.deleted, out.unmatched, out.rejected
        db.commit()
        out.log_id = sync_log.id
        log.info("busy sync %s %s: received=%s inserted=%s updated=%s unchanged=%s deleted=%s unmatched=%s rejected=%s",
                 source, out.status, out.received, out.inserted, out.updated, out.unchanged, out.deleted, out.unmatched, out.rejected)
        return out
    except Exception as exc:
        db.rollback()
        log.exception("busy sync %s failed", source)
        if not dry_run:
            record_failure(db, started=started, source=source, mode=mode, period=period, triggered_by=triggered_by, received=len(entries),
                           message=f"Internal error while saving ({type(exc).__name__}); nothing was changed. See the server log.")
        raise


def record_failure(db: Session, *, started: datetime, source: str, mode: str | None, period: tuple[date, date] | None, triggered_by: str | None,
                   received: int, message: str) -> BusySyncLog:
    """A SyncLog row for a call that could not be processed at all (bad request body, internal error). Commits on its own."""
    entry = BusySyncLog(started_at=started, finished_at=datetime.now(timezone.utc), source=source, mode=mode,
                        period_from=period[0] if period else None, period_to=period[1] if period else None,
                        triggered_by=(triggered_by or "")[:120] or None, rows_received=received, status=STATUS_FAILED, error_message=message[:1000])
    db.add(entry)
    db.commit()
    return entry
