"""
Import / refresh stores from the partner outlet-master Google Sheets.

Each sheet is read through its public CSV export endpoint
(https://docs.google.com/spreadsheets/d/<id>/export?format=csv&gid=<gid>),
so the sheet must be shared as "Anyone with the link - Viewer" or Published
to web. No Google credentials are used or stored.

Match key: (partner_organization, external_code) == (platform, Outlet ID).
Rows are upserted; a store already in the CRM but absent from the sheet is
left untouched (the sheet only adds / updates, never deletes).
Credential columns in the sheet (logins / passwords) are deliberately ignored.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.error
import urllib.request
import uuid
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.organization import Organization, OrganizationKind
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.services import activity_service, assignment_service, store_service, vendor_history_service

_CSV_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

# Sheet header -> Store field. Header lookup is case-insensitive and
# whitespace-trimmed; the first alias that is present wins.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "external_code": ["outlet id", "outlet_id", "store id", "store code", "outlet code", "id"],
    "name": ["outlet name", "store name", "outlet", "name"],
    "region": ["zone", "region"],
    "entity": ["entity"],
    # Veekay's own start date wins; fall back to the partner's go-live date column.
    "start_date": ["start date", "start_date", "start date by blinkit", "supply start date", "go-live date", "go live date", "live date"],
    "state": ["state"],
    "city": ["city"],
    "address": ["address", "location"],
    "status": ["status"],
    "poc_name": ["poc name", "poc", "store manager name", "store maneger name", "store manager", "manager name"],
    "poc_number": ["poc contact no", "poc contact", "poc number", "poc contact number", "poc no",
                   "store manager number", "manager number", "number", "phone", "mobile"],
    "vendor_name": ["vendor", "vendor name"],
    "vendor_number": ["contact details", "vendor contact", "vendor number", "vendor contact no", "contact number"],
}

# Order matters: "not live yet" / "inactive" must be caught before the bare
# words "live" / "active" would claim them. Whole-word matches only, so
# e.g. "deliver" never counts as "live".
_PENDING_FIRST = re.compile(
    r"\b(yet to|not (yet )?(live|started|active)|to go live|to be live|awaiting|await|pending|"
    r"on[- ]?hold|hold|in[- ]?progress|in process|onboarding|upcoming)\b"
)
_CLOSE_RE = re.compile(
    r"\b(closed?|inactive|stopped|stop|churn(ed)?|terminated|discontinued|dead|lost|shut( down)?)\b"
)
_LIVE_RE = re.compile(r"\b(live|active|running|working|operational|go[- ]?live)\b")


def parse_status(raw: str | None) -> str | None:
    """Free-text sheet status -> LIVE / PENDING / CLOSE, or None when the cell is blank or says something we don't know."""
    if not raw or not raw.strip():
        return None
    text = raw.strip().lower()
    if _PENDING_FIRST.search(text):
        return StoreStatus.PENDING.value
    if _CLOSE_RE.search(text):
        return StoreStatus.CLOSE.value
    if _LIVE_RE.search(text):
        return StoreStatus.LIVE.value
    return None


def normalize_status(raw: str | None) -> str:
    """Status for a NEW store. Blank / unknown -> PENDING so it surfaces for review rather than silently going live."""
    return parse_status(raw) or StoreStatus.PENDING.value


@dataclass
class SyncResult:
    platform: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rows_read: int = 0
    vendor_changes: int = 0     # stores whose vendor changed (the old vendor is kept as history)
    without_start_date: int = 0  # new stores added although the sheet had no readable start date
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "vendor_changes": self.vendor_changes,
            "without_start_date": self.without_start_date,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "rows_read": self.rows_read,
            "warnings": self.warnings[:50],
        }


# --------------------------------------------------------------------------


def fetch_csv_text(sheet_id: str, gid: str) -> str:
    """Download one tab of a public Google Sheet as CSV text. Raises SyncError with a readable reason."""
    url = _CSV_URL.format(sheet_id=sheet_id, gid=gid)
    from app.services import google_sheets

    if google_sheets.configured():   # private sheet shared with our service account
        try:
            return google_sheets.fetch_csv(url)
        except google_sheets.SheetsAccessError as exc:
            raise SyncError(str(exc)) from None
    req = urllib.request.Request(url, headers={"User-Agent": "veekay-crm-store-sync/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed docs.google.com host
            body = resp.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SyncError(
                "The sheet is not publicly readable. Share it as "
                "'Anyone with the link - Viewer' (or File - Share - Publish to web)."
            ) from exc
        raise SyncError(f"Google Sheets returned HTTP {exc.code} for this sheet.") from exc
    except urllib.error.URLError as exc:
        raise SyncError(f"Could not reach Google Sheets: {exc.reason}") from exc
    return body


def _fetch_rows(sheet_id: str, gid: str) -> list[dict[str, str]]:
    return _parse_csv_text(fetch_csv_text(sheet_id, gid))


def _parse_csv_text(body: str) -> list[dict[str, str]]:
    reader = csv.reader(io.StringIO(body))
    try:
        header = next(reader)
    except StopIteration:
        return []
    keys = _trim_header([h.strip() for h in header])
    return _collect_rows(keys, (row for row in reader), lambda c: c.strip() if isinstance(c, str) else c)


log = logging.getLogger("veekay.store_import")


def _rss_mb() -> int | None:
    """This process's resident memory (Linux only; None elsewhere). Logged per import phase so a memory problem
    shows WHERE it grows, instead of just an out-of-memory kill."""
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# A small .xlsx can unpack to a huge XML (a zip bomb, or a sheet formatted down to the last row / out to the last
# column). These limits keep one import's memory and CPU bounded no matter what the file contains.
MAX_UNPACKED_BYTES = 60 * 1024 * 1024
MAX_ROWS = 20_000            # data rows; a real outlet list is a few thousand
MAX_COLUMNS = 120
BLANK_ROWS_STOP = 500        # this many blank rows in a row = the data has ended (formatting continues below it)
MAX_CELL_CHARS = 1_000
STORE_FLUSH_EVERY = 500      # new stores are written to the database in batches of this size

# Column widths from the Store model. Real sheets have long free-text cells
# (multi-line addresses, several phone numbers in one cell); trim instead of
# letting one cell fail the whole import with a database error.
_FIELD_LIMITS = {
    "name": 128, "entity": 64, "state": 64, "city": 64, "address": 255,
    "poc_name": 128, "poc_number": 32, "vendor_name": 128, "vendor_number": 32,
}
_CODE_LIMIT = 64


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # phone numbers / ids Excel stored as floats
    return str(value)


def _trim_header(keys: list[str]) -> list[str]:
    """Drop empty trailing header cells (a sheet formatted out to column XFD has thousands) and cap the width."""
    while keys and not keys[-1]:
        keys.pop()
    if len(keys) > MAX_COLUMNS:
        raise SyncError(f"The sheet has more than {MAX_COLUMNS} columns. Remove the extra columns and try again.")
    return keys


def _collect_rows(keys: list[str], rows, to_text) -> list[dict[str, str]]:
    """Stream rows into dicts, reading only the header's width, stopping after a long run of blank rows, and
    refusing absurd sizes: memory stays proportional to the real data, never to what the sheet declares."""
    width = len(keys)
    out: list[dict[str, str]] = []
    blank_run = 0
    for row in rows:
        cells = [_cell_text(to_text(c))[:MAX_CELL_CHARS] for c in row[:width]]
        if not any(c.strip() for c in cells):
            blank_run += 1
            if blank_run >= BLANK_ROWS_STOP:
                break
            continue
        blank_run = 0
        if len(out) >= MAX_ROWS:
            raise SyncError(f"The sheet has more than {MAX_ROWS:,} rows. Split it into smaller files.")
        out.append(dict(zip(keys, cells)))
    return out


def bounded_rows(rows, error_cls=None):
    """Yield rows from a worksheet iterator, but never an unbounded number: stop after a long run of blank rows (sheets
    formatted down to the last row), and refuse a sheet with more than MAX_ROWS rows of data. Used by every importer."""
    error_cls = error_cls or SyncError
    count = 0
    blank_run = 0
    for row in rows:
        if any(c is not None and str(c).strip() for c in row):
            blank_run = 0
        else:
            blank_run += 1
            if blank_run >= BLANK_ROWS_STOP:
                return
        count += 1
        if count > MAX_ROWS + BLANK_ROWS_STOP:
            raise error_cls(f"The sheet has more than {MAX_ROWS:,} rows. Split it into smaller files.")
        yield row


def _check_unpacked_size(content: bytes) -> None:
    """Refuse an .xlsx that unpacks far beyond its upload size, before anything is decompressed."""
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            unpacked = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile as exc:
        raise SyncError("That file could not be read as an Excel workbook.") from exc
    if unpacked > MAX_UNPACKED_BYTES:
        raise SyncError(
            f"That workbook unpacks to {unpacked // (1024 * 1024)} MB, which is too large to import safely. "
            "Open it in Excel, copy the outlet table into a new file, and upload that."
        )


def _rows_from_xlsx(content: bytes) -> list[dict[str, str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise SyncError("Excel files need the 'openpyxl' package on the server.") from exc
    _check_unpacked_size(content)
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a bad file
        raise SyncError("That file could not be read as an Excel workbook.") from exc
    try:
        it = wb.active.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            return []
        keys = _trim_header([_cell_text(h).strip()[:MAX_CELL_CHARS] for h in header])
        return _collect_rows(keys, it, lambda c: c)
    finally:
        wb.close()


def rows_from_upload(filename: str, content: bytes) -> list[dict[str, str]]:
    if len(content) > MAX_UPLOAD_BYTES:
        raise SyncError("That file is too large (limit is 5 MB).")
    name = (filename or "").lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        return _parse_csv_text(content.decode("utf-8-sig", "replace"))
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return _rows_from_xlsx(content)
    raise SyncError("Upload a .csv or .xlsx file.")


def _resolve_columns(sample: dict[str, str]) -> dict[str, str]:
    """{store_field: actual_header} for headers present in the sheet."""
    lower_to_actual = {k.strip().lower(): k for k in sample}
    resolved: dict[str, str] = {}
    for field_name, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_to_actual:
                resolved[field_name] = lower_to_actual[alias]
                break
    return resolved


_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
)


def _parse_date(raw: str | None) -> date | None:
    """Sheet cell -> date. Day-first for ambiguous forms (Indian sheets); Excel serials accepted."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    parsed: date | None = None
    if text.isdigit() and 30000 <= int(text) <= 70000:  # Excel serial day number
        parsed = date(1899, 12, 30) + timedelta(days=int(text))
    else:
        for candidate in (text, text[:10]):  # "2026-09-01 00:00:00" -> first 10 chars
            for fmt in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(candidate, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed:
                break
    if parsed is None or not (2015 <= parsed.year <= date.today().year + 2):
        return None
    return parsed


_name_key = store_service.name_key      # a store's name is its identity; capitals and extra spaces do not matter


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v or None


# --------------------------------------------------------------------------


class SyncError(Exception):
    """Raised for a whole-sheet failure (bad URL, private sheet, missing key column)."""


def _create_region(
    db: Session, org_id: uuid.UUID, name: str, cache: dict[str, Region]
) -> Region:
    name = name.strip()[:128]
    base_code = "".join(c for c in name.upper() if c.isalnum())[:24] or "REGION"
    code = base_code
    n = 1
    existing_codes = {r.code for r in cache.values()}
    while code in existing_codes:
        n += 1
        code = f"{base_code[:22]}{n}"
    region = Region(organization_id=org_id, name=name, code=code, is_active=True)
    db.add(region)
    db.flush()
    cache[name.lower()] = region
    return region


def sync_platform(db: Session, actor: User, partner_slug: str) -> SyncResult:
    partner_slug = partner_slug.strip().lower()
    sources = settings.sheet_sources()
    if partner_slug not in sources:
        raise SyncError(f"No sheet is configured for '{partner_slug}'. Set STORE_SYNC_SHEETS.")
    sheet_id, gid = sources[partner_slug]

    partner = db.execute(
        select(Organization).where(
            Organization.slug == partner_slug,
            Organization.kind == OrganizationKind.PARTNER.value,
        )
    ).scalar_one_or_none()
    if partner is None:
        raise SyncError(f"'{partner_slug}' is not a configured platform in the CRM.")

    return _import_rows(db, actor, partner, partner_slug, _fetch_rows(sheet_id, gid), source="sheet")


def import_file(
    db: Session, actor: User, partner_slug: str, filename: str, content: bytes, *, allow_mismatch: bool = False
) -> SyncResult:
    """Import stores for one platform from an uploaded CSV / Excel file."""
    partner_slug = partner_slug.strip().lower()
    partner = db.execute(
        select(Organization).where(
            Organization.slug == partner_slug,
            Organization.kind == OrganizationKind.PARTNER.value,
        )
    ).scalar_one_or_none()
    if partner is None:
        raise SyncError(f"'{partner_slug}' is not a configured platform in the CRM.")
    log.info("store import start", extra={"platform": partner_slug, "bytes": len(content), "rss_mb": _rss_mb()})
    rows = rows_from_upload(filename, content)
    log.info("store import parsed", extra={"platform": partner_slug, "rows": len(rows), "rss_mb": _rss_mb()})
    return _import_rows(db, actor, partner, partner_slug, rows, source="file", allow_mismatch=allow_mismatch)


_MISMATCH_SHARE = 0.5   # this share of rows pointing at another platform blocks the import


def _check_platform_match(db: Session, partner: Organization, cols: dict, rows: list[dict[str, str]]) -> None:
    """Refuse a sheet that clearly belongs to a different platform (e.g. the Zepto outlet list picked as Blinkit).
    Two independent signals, either one blocks:
      1. rows whose Outlet ID / Name mention ANOTHER platform's name and never this one's;
      2. Outlet IDs that already exist under another platform (and not under this one).
    """
    sample = [(_clean(r.get(cols["external_code"])), _clean(r.get(cols["name"]))) for r in rows]
    sample = [(c, n) for c, n in sample if c and n]
    if len(sample) < 3:
        return
    others = db.execute(
        select(Organization).where(
            Organization.kind == OrganizationKind.PARTNER.value, Organization.id != partner.id, Organization.is_active.is_(True)
        )
    ).scalars().all()

    def mentions(org: Organization, c: str, n: str) -> bool:
        text = f"{c} {n}".lower()
        return org.slug.lower() in text or org.name.strip().lower() in text

    this_hits = sum(1 for c, n in sample if mentions(partner, c, n))
    for org in others:
        hits = sum(1 for c, n in sample if mentions(org, c, n))
        if hits / len(sample) >= _MISMATCH_SHARE and this_hits / len(sample) < 0.2:
            raise SyncError(
                f"This looks like a {org.name} sheet ({hits} of {len(sample)} rows mention {org.name}), but you chose "
                f"{partner.name}. Pick {org.name} instead. Nothing was imported."
            )

    codes = [c for c, _ in sample]
    mine = set(db.execute(
        select(Store.external_code).where(Store.partner_organization_id == partner.id, Store.external_code.in_(codes))
    ).scalars())
    for org in others:
        theirs = set(db.execute(
            select(Store.external_code).where(Store.partner_organization_id == org.id, Store.external_code.in_(codes))
        ).scalars()) - mine
        if len(theirs) >= 3 and len(theirs) / len(sample) >= _MISMATCH_SHARE:
            raise SyncError(
                f"{len(theirs)} of {len(sample)} Outlet IDs in this sheet already exist as {org.name} stores, but you chose "
                f"{partner.name}. This is probably the {org.name} sheet. Nothing was imported."
            )


def _import_rows(
    db: Session,
    actor: User,
    partner: Organization,
    partner_slug: str,
    rows: list[dict[str, str]],
    *,
    source: str,
    allow_mismatch: bool = False,
) -> SyncResult:
    result = SyncResult(platform=partner_slug, rows_read=len(rows))
    if not rows:
        result.warnings.append("The sheet has no data rows.")
        return result

    cols = _resolve_columns(rows[0])
    if "external_code" not in cols or "name" not in cols:
        raise SyncError(
            "Could not find the 'Outlet ID' and 'Outlet Name' columns in the sheet header."
        )

    if not allow_mismatch:
        _check_platform_match(db, partner, cols, rows)

    regions_by_name = {
        r.name.strip().lower(): r
        for r in db.execute(
            select(Region).where(Region.organization_id == actor.organization_id)
        ).scalars()
    }
    # One query for every store of this platform; the loop below then touches the database only to insert/update
    # in bulk at the end (a per-row lookup + flush was ~2 round trips per row: minutes on a remote database).
    # The store NAME is its identity: a row finds its store by name. A store made under a temporary Outlet ID is therefore found
    # again when the real ID arrives and simply gets that ID. The Outlet ID may repeat (two stores can share one); the repeats
    # are listed under Stores > Duplicates for someone to correct. The sheet's start date is NOT used: a store's start date
    # comes from its first order (or from the manual add form).
    stores_by_name: dict[str, list[Store]] = {}
    for st in db.execute(select(Store).where(Store.partner_organization_id == partner.id)).scalars():
        stores_by_name.setdefault(_name_key(st.name), []).append(st)
    seen_names: set[str] = set()          # names already handled in this sheet: a name appears once
    issues: list[dict] = []               # rows someone has to sort out; kept with the import so Stores > Duplicates can list them

    def issue(row_no: int, name: str | None, code: str | None, reason: str, detail: str = "") -> None:
        issues.append({"row": row_no, "name": name, "code": code, "reason": reason, "detail": detail})
    renamed: list[tuple[str, str]] = []   # (old Outlet ID, new Outlet ID)
    renamed_ids: set[uuid.UUID] = set()
    status_changes: list[tuple[Store, str]] = []
    trimmed: dict[str, list[int]] = {}  # field -> sheet rows that were cut to fit
    vendor_touched: list[Store] = []     # stores whose vendor was set or changed by this import
    unknown_status: list[int] = []       # rows whose status text isn't recognised (existing stores keep their status)

    for i, row in enumerate(rows, start=2):  # sheet row number (1 = header)
        code = _clean(row.get(cols["external_code"]))
        name = _clean(row.get(cols["name"]))
        if not code or not name:
            if code or name:
                issue(i, name, code, "missing_name_or_id", "The row has an Outlet ID but no Outlet Name, or the other way round, so it was not imported.")
            continue
        if len(code) > _CODE_LIMIT:
            result.warnings.append(f"Row {i}: Outlet ID is longer than {_CODE_LIMIT} characters — skipped.")
            issue(i, name, code, "id_too_long", f"The Outlet ID is longer than {_CODE_LIMIT} characters, so the row was not imported.")
            continue

        raw_status = row.get(cols["status"]) if "status" in cols else None
        status = parse_status(raw_status)          # None: blank or unrecognised -> an existing store keeps its status
        if status is None and _clean(raw_status):
            unknown_status.append(i)
            issue(i, name, code, "status_not_understood", f"Status '{_clean(raw_status)}' is not Live, Pending or Close. A new store is added as Pending; an existing store keeps its status.")
        region_id: uuid.UUID | None = None
        if "region" in cols:
            raw_region = _clean(row.get(cols["region"]))
            if raw_region:
                key = raw_region.lower().replace(" zone", "").strip()
                base = re.sub(r"\s*\d+$", "", key).strip()  # "South 2" -> "south"
                region = regions_by_name.get(key) or regions_by_name.get(raw_region.lower()) or regions_by_name.get(base)
                if region is None and assignment_service.is_employee_model(partner_slug):
                    pass  # employee-model platforms (Zepto) are scoped by state, not region — never invent regions
                elif region is None:
                    region = _create_region(db, actor.organization_id, raw_region, regions_by_name)
                    result.warnings.append(f"Row {i}: created new region '{region.name}' from zone '{raw_region}'.")
                region_id = region.id if region is not None else None

        fields = {
            "name": name,
            "entity": _clean(row.get(cols["entity"])) if "entity" in cols else None,
            "state": _clean(row.get(cols["state"])) if "state" in cols else None,
            "city": _clean(row.get(cols["city"])) if "city" in cols else None,
            "address": _clean(row.get(cols["address"])) if "address" in cols else None,
            "poc_name": _clean(row.get(cols["poc_name"])) if "poc_name" in cols else None,
            "poc_number": _clean(row.get(cols["poc_number"])) if "poc_number" in cols else None,
            "vendor_name": _clean(row.get(cols["vendor_name"])) if "vendor_name" in cols else None,
            "vendor_number": _clean(row.get(cols["vendor_number"])) if "vendor_number" in cols else None,
            "status": status,
            "region_id": region_id,
        }
        if status is None:
            fields.pop("status")                   # not written for existing stores; a new store defaults to PENDING

        for fname, limit in _FIELD_LIMITS.items():
            val = fields.get(fname)
            if isinstance(val, str) and len(val) > limit:
                fields[fname] = val[:limit].rstrip()
                trimmed.setdefault(fname, []).append(i)

        key = _name_key(name)
        if key in seen_names:
            result.warnings.append(f"Row {i}: the store name '{name}' appears more than once in this sheet — only the first row was used.")
            issue(i, name, code, "name_repeated_in_sheet", "This name is on an earlier row of the sheet, so this row was not imported. If it is a different outlet it needs its own name; if it is the same outlet, remove the extra row.")
            continue
        seen_names.add(key)
        twins = stores_by_name.get(key, [])
        existing = None
        if len(twins) == 1:
            existing = twins[0]
        elif len(twins) > 1:
            same_id = [t for t in twins if t.external_code == code]
            if len(same_id) == 1:
                existing = same_id[0]
            else:
                result.warnings.append(
                    f"Row {i}: {len(twins)} stores are already named '{name}' — not changed. Merge or correct them under Stores > Duplicates."
                )
                issue(i, name, code, "name_matches_several_stores", f"{len(twins)} stores in the CRM already have this name and none has Outlet ID {code}, so nothing was changed. Merge the extra copies, or correct their Outlet IDs.")
                continue
        if existing is not None and existing.external_code != code:
            renamed.append((existing.external_code, code))          # the real Outlet ID replaces the temporary one
            existing.external_code = code
            renamed_ids.add(existing.id)

        if existing is None:
            new_store = Store(
                organization_id=actor.organization_id,
                partner_organization_id=partner.id,
                external_code=code,
                **{"status": StoreStatus.PENDING.value, **fields},
            )
            db.add(new_store)
            if (new_store.vendor_name or "").strip():
                vendor_touched.append(new_store)
            result.created += 1
            if result.created % STORE_FLUSH_EVERY == 0:
                db.flush()   # bounded batches instead of one giant statement; still one transaction, committed at the end
        else:
            fields.pop("name", None)                  # a store's name is never changed by an import
            changed = existing.id in renamed_ids      # a new Outlet ID is an update by itself
            old_status = existing.status
            old_vendor = existing.vendor_name
            for k, v in fields.items():
                # don't wipe a manually-filled field when the sheet cell is blank
                if v is None and getattr(existing, k) is not None and k != "status":
                    continue
                if getattr(existing, k) != v:
                    setattr(existing, k, v)
                    changed = True
            if existing.status != old_status:
                status_changes.append((existing, old_status))
            if (existing.vendor_name or "").strip() and not vendor_history_service.same_vendor(old_vendor, existing.vendor_name):
                vendor_touched.append(existing)
            if changed:
                result.updated += 1
            else:
                result.unchanged += 1

    db.flush()
    result.vendor_changes = vendor_history_service.record_vendors(
        db, vendor_touched, source=source, today=datetime.now(timezone.utc).date(), changed_by=actor.full_name
    )
    if result.vendor_changes:
        result.warnings.append(
            f"{result.vendor_changes} store{'s' if result.vendor_changes > 1 else ''} changed vendor; the previous vendor is kept "
            "in the store's history. The new vendor's start date is set from the first order sheet import."
        )
    log.info("store import written", extra={"platform": partner_slug, "stores_created": result.created, "rss_mb": _rss_mb()})
    store_service.record_status_changes(db, actor, status_changes)
    if result.created:
        restored = store_service.restore_archived_history(db, actor.organization_id, partner.id)
        if restored:
            result.warnings.append(f"{restored} archived order days were restored to re-added stores.")
            vendor_history_service.set_start_dates_from_orders(db, partner.id)   # restored history dates the new stores

    if renamed:
        shown = ", ".join(f"{a} → {b}" for a, b in renamed[:6]) + (" …" if len(renamed) > 6 else "")
        result.warnings.insert(
            0,
            f"{len(renamed)} store{'s were' if len(renamed) > 1 else ' was'} matched by Outlet Name and got the Outlet ID from the sheet "
            f"instead of being added again ({shown}). Their orders, documents and history stayed with them.",
        )
    repeats = db.execute(
        select(func.count()).select_from(
            select(Store.external_code).where(Store.partner_organization_id == partner.id)
            .group_by(Store.external_code).having(func.count() > 1).subquery()
        )
    ).scalar_one()
    if repeats:
        result.warnings.append(
            f"{repeats} Outlet ID{'s are' if repeats > 1 else ' is'} used by more than one store. The stores were kept; "
            "see Stores > Duplicates to correct them."
        )
    if unknown_status:
        n = len(unknown_status)
        result.warnings.append(
            f"{n} row{'s' if n > 1 else ''} had a status the CRM doesn't recognise (first: row {unknown_status[0]}). "
            "Existing stores kept their current status; new stores were added as Pending. Use Live, Pending or Close."
        )
    for fname, rows_hit in trimmed.items():
        result.warnings.append(
            f"{len(rows_hit)} row{'s' if len(rows_hit) > 1 else ''} had a '{fname}' value longer than "
            f"{_FIELD_LIMITS[fname]} characters and was trimmed (first: row {rows_hit[0]})."
        )

    activity_service.record(
        db, actor=actor, action="store.synced", entity_type="store", entity_id=partner.id,
        metadata={
            "platform": partner_slug,
            "source": source,
            "created": result.created,
            "updated": result.updated,
            "rows_read": result.rows_read,
            "ids_renamed_by_name": [{"from": a, "to": b} for a, b in renamed[:200]],
            "issue_count": len(issues),
            "issues": issues[:300],
        },
    )
    db.commit()
    return result


def sync_all(db: Session, actor: User) -> list[SyncResult]:
    out: list[SyncResult] = []
    for slug in settings.sheet_sources():
        try:
            out.append(sync_platform(db, actor, slug))
        except SyncError as exc:
            r = SyncResult(platform=slug)
            r.warnings.append(str(exc))
            out.append(r)
    return out
