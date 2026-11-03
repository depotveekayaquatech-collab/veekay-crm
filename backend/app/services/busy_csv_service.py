"""
Manual CSV upload for vendor payments. Turns a file plus a column mapping into the same row dicts the API takes, then hands them to the shared
sync routine (busy_sync_service), so a CSV import validates, matches and upserts exactly like an API call.
"""
import csv
import io
import json
import re

from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.busy_ledger import CsvPreview
from app.services.busy_sync_service import SyncOutcome

FIELDS = ("account_name", "vendor_code", "date", "type", "amount", "voucher_no", "narration")
REQUIRED = ("date", "type", "amount", "voucher_no")           # plus vendor_code or account_name
TEMPLATE_ROWS = [
    ["Sharma Traders Gurugram V0123", "", "2026-10-03", "BILL", "125000.00", "PUR/0451", "Water bottles, October lot 1"],
    ["Sharma Traders Gurugram V0123", "", "2026-10-12", "PAYMENT", "50000.00", "PAY/0212", "Part payment by bank transfer"],
    ["", "V0456", "2026-10-15", "BILL", "8400.50", "PUR/0460", "Account name left blank because the code is given"],
]
_ALIASES = {
    "account_name": ("accountname", "account", "party", "partyname", "ledger", "ledgername", "vendor", "vendorname", "name"),
    "vendor_code": ("vendorcode", "code", "partycode", "accountcode"),
    "date": ("date", "entrydate", "voucherdate", "txndate", "transactiondate"),
    "type": ("type", "entrytype", "vouchertype", "vchtype", "vchrtype", "kind"),
    "amount": ("amount", "amt", "value", "total"),
    "voucher_no": ("voucherno", "voucher", "vouchernumber", "vchno", "vchrno", "billno", "reference", "ref"),
    "narration": ("narration", "remarks", "remark", "description", "note", "notes"),
}


def template_csv() -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(FIELDS)
    writer.writerows(TEMPLATE_ROWS)
    return out.getvalue()


def _simple(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def read_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    """(header names, data rows) from the uploaded bytes. Blank rows are skipped. Reads UTF-8 (with or without BOM), else Windows-1252 as Excel saves it."""
    if len(data) > settings.BUSY_CSV_MAX_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"That file is larger than {settings.BUSY_CSV_MAX_MB} MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file is empty.")
    headers, body = rows[0], rows[1:]
    if len(body) > settings.BUSY_SYNC_MAX_ROWS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"At most {settings.BUSY_SYNC_MAX_ROWS} rows per upload; split the file.")
    return headers, body


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """Our field -> the file's column header, by common names. First column wins; a column is never used for two fields."""
    taken: set[str] = set()
    mapping: dict[str, str | None] = {}
    for field in FIELDS:
        names = (_simple(field),) + _ALIASES[field]
        found = next((h for h in headers if h not in taken and _simple(h) in names), None)
        mapping[field] = found
        if found:
            taken.add(found)
    return mapping


def parse_mapping(raw: str, headers: list[str]) -> dict[str, str | None]:
    """The mapping the admin chose (JSON {field: header}); blank means 'guess'. Unknown fields or headers are a 422."""
    if not raw.strip():
        return suggest_mapping(headers)
    try:
        chosen = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The column mapping is not valid JSON.") from exc
    if not isinstance(chosen, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The column mapping must be an object of field to column.")
    mapping: dict[str, str | None] = {field: None for field in FIELDS}
    for field, header in chosen.items():
        if field not in FIELDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown field '{field}'.")
        if header in (None, ""):
            continue
        if header not in headers:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The file has no column '{header}'.")
        mapping[field] = header
    return mapping


def missing_fields(mapping: dict[str, str | None]) -> list[str]:
    missing = [f for f in REQUIRED if not mapping.get(f)]
    if not mapping.get("vendor_code") and not mapping.get("account_name"):
        missing.append("vendor_code or account_name")
    return missing


def to_entries(headers: list[str], body: list[list[str]], mapping: dict[str, str | None]) -> list[dict[str, str]]:
    position = {field: headers.index(header) for field, header in mapping.items() if header}
    return [{field: (row[i] if i < len(row) else "") for field, i in position.items()} for row in body]


def preview(headers: list[str], body: list[list[str]], mapping: dict[str, str | None], outcome: SyncOutcome | None) -> CsvPreview:
    return CsvPreview(headers=headers, mapping=mapping, missing_fields=missing_fields(mapping), total_rows=len(body),
                      result=outcome.to_dict() if outcome else None)

