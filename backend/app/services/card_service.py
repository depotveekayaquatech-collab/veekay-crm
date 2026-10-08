"""
Monthwise virtual cards: one PDF per vendor, one A4 card per LIVE store of that vendor.

This reproduces the original Apps Script ("Vendor Standard Cards") rules exactly:

  BLANK card      — a "Month of – ________" write-in line on top; the two log tables are empty.
  CARD WITH ENTRY — "Month of – SEP-2026"; the tables are pre-filled, row by row in order, with the
                    Date and Filled-bottle count of every day that has an entry (a marked 0 counts),
                    and TOTAL COUNT. Empty-bottle and Signature columns always stay blank.

  Card layout     — month line / company band (name, email, contact number) / logo | title, channel,
                    vendor | QR / store details (name, outlet ID, entity, region, state, city) /
                    two log tables of 15 and 16 rows, the second ending in TOTAL COUNT.
  Contact number  — Blinkit: the phone(s) of the active employee(s) of the store's REGION (max 2,
                    joined with " / "); Zepto: the employee the store's STATE is assigned to.
                    Number only, no name.
  QR code         — HMAC-signed link to a public page with the store's bottle count for this month
                    (till date) and last month (only once last month is on/after CARDS_FIRST_MONTH).

Who may print: admins any store on a platform; employees only the stores assigned to them.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import io
import re
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.region import Region
from app.models.state_assignment import StateAssignment
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.services import assignment_service

NO_VENDOR = "No vendor"
MAX_STORES_PER_PDF = 600
MAX_STORES_PER_ZIP = 1500
MAX_CONTACTS_ON_CARD = 2

# palette of the original card (blue theme)
C_MAIN = (0x0B / 255, 0x6F / 255, 0xB8 / 255)    # #0B6FB8
C_DARK = (0x08 / 255, 0x4B / 255, 0x7C / 255)    # #084B7C
C_LIGHT = (0xE8 / 255, 0xF2 / 255, 0xFA / 255)   # #E8F2FA
C_BORDER = (0xCF / 255, 0xD6 / 255, 0xD3 / 255)  # #CFD6D3
C_GRID = (0x8A / 255, 0x8A / 255, 0x8A / 255)    # #8A8A8A
C_MUTED = (0.4, 0.4, 0.4)
C_TEXT = (0.07, 0.07, 0.07)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def month_label(d: date) -> str:
    """'SEP-2026' — the label printed on cards and the public page."""
    return f"{calendar.month_abbr[d.month].upper()}-{d.year}"


def first_month() -> date:
    y, m = (int(x) for x in settings.CARDS_FIRST_MONTH.split("-"))
    return date(y, m, 1)


def _prev_month(d: date) -> date:
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def available_months() -> list[dict]:
    """Months a card can be filled for: this month (till date) and every earlier month back to the first active one."""
    cur = _today().replace(day=1)
    out, m = [], cur
    while m >= first_month():
        out.append({"value": f"{m:%Y-%m}", "label": month_label(m) + (" (till date)" if m == cur else " (full month)")})
        m = _prev_month(m)
    return out


def parse_card_month(value: str | None) -> date | None:
    """None = blank cards. Otherwise a YYYY-MM between the first active month and this month."""
    if not value:
        return None
    try:
        y, m = (int(x) for x in value.split("-"))
        d = date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-09.") from exc
    if d > _today().replace(day=1) or d < first_month():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Choose a month from {month_label(first_month())} to {month_label(_today().replace(day=1))}, or leave it blank.",
        )
    return d


# --------------------------------------------------------------------------
# signing / public count
# --------------------------------------------------------------------------

def _secret() -> bytes:
    return hashlib.sha256(b"qr|" + (settings.QR_SIGNING_SECRET or settings.JWT_SECRET_KEY).encode()).digest()


def sign_store(store_id: uuid.UUID | str) -> str:
    return hmac.new(_secret(), f"count:{store_id}".encode(), hashlib.sha256).hexdigest()[:32]


def verify_signature(store_id: uuid.UUID | str, sig: str) -> bool:
    return hmac.compare_digest(sign_store(store_id), (sig or "").lower())


def qr_url(store_id: uuid.UUID) -> str:
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}/count?s={store_id}&sig={sign_store(store_id)}"


def _month_total(db: Session, store_id: uuid.UUID, start: date, end: date) -> int:
    return int(db.execute(
        select(func.coalesce(func.sum(OrderEntry.bottle_count), 0)).where(
            OrderEntry.store_id == store_id, OrderEntry.order_date >= start, OrderEntry.order_date <= end
        )
    ).scalar_one())


def public_count(db: Session, store_id: uuid.UUID, sig: str) -> dict:
    """The page the QR opens: bottles supplied this month (till date) and, when available, last month. Totals only."""
    if not verify_signature(store_id, sig):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This QR code isn't valid.")
    store = db.execute(
        select(Store).where(Store.id == store_id).options(joinedload(Store.partner_organization))
    ).unique().scalar_one_or_none()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This QR code isn't valid.")

    today = _today()
    cur = today.replace(day=1)
    prev = _prev_month(cur)
    out = {
        "store_name": store.name, "store_code": store.external_code, "vendor_name": store.vendor_name,
        "platform": store.partner_organization.name if store.partner_organization else None,
        "this_month_label": month_label(cur), "this_month_bottles": _month_total(db, store.id, cur, today),
        "last_month_label": None, "last_month_bottles": None,
        "as_on": datetime.now(timezone.utc),
    }
    if prev >= first_month():  # "last month" only appears once the previous month is an active one
        out["last_month_label"] = month_label(prev)
        out["last_month_bottles"] = _month_total(db, store.id, prev, date(prev.year, prev.month, calendar.monthrange(prev.year, prev.month)[1]))
    return out


# --------------------------------------------------------------------------
# store selection + vendors
# --------------------------------------------------------------------------

def _stores(db: Session, user: User, *, is_admin: bool, partner: str | None, region: uuid.UUID | None = None) -> list[Store]:
    if is_admin:
        stmt = (
            select(Store)
            .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
            .order_by(Store.name)
        )
        if partner:
            stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
        if region:
            stmt = stmt.where(Store.region_id == region)
        return list(db.execute(stmt).unique().scalars().all())
    rows = assignment_service.visible_stores(db, user)
    if partner:
        rows = [s for s in rows if s.partner_organization and s.partner_organization.slug == partner]
    if region:
        rows = [s for s in rows if s.region_id == region]
    return sorted(rows, key=lambda s: s.name.lower())


def _vendor_key(s: Store) -> str:
    return (s.vendor_name or "").strip() or NO_VENDOR


MAX_MATCHES = 5


def _store_text(s: Store) -> str:
    return " ".join(filter(None, [
        s.name, s.external_code, s.city, s.state, s.address, s.entity,
        s.poc_name, s.poc_number, s.vendor_name, s.vendor_number,
    ])).lower()


def _store_digits(s: Store) -> str:
    return " ".join(re.sub(r"\D", "", x or "") for x in (s.poc_number, s.vendor_number, s.external_code))


def list_regions(db: Session, user: User, *, is_admin: bool, partner: str | None) -> list[dict]:
    """Regions that have live stores on the chosen platform — the Region dropdown follows the Platform dropdown."""
    if is_admin:
        # Straight from the database: no need to load ~1,300 store objects to list a handful of regions.
        stmt = (
            select(Region.id, Region.name)
            .select_from(Store)
            .join(Region, Region.id == Store.region_id)
            .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
            .group_by(Region.id, Region.name)
        )
        if partner:
            stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
        return sorted(({"id": i, "name": n} for i, n in db.execute(stmt).all()), key=lambda r: r["name"].lower())
    seen = {s.region.id: s.region.name for s in _stores(db, user, is_admin=is_admin, partner=partner) if s.region}
    return sorted(({"id": i, "name": n} for i, n in seen.items()), key=lambda r: r["name"].lower())


def list_vendors(
    db: Session, user: User, *, is_admin: bool, partner: str | None, region: uuid.UUID | None = None, q: str | None = None,
) -> list[dict]:
    """Vendors with their live-store counts. With `q`, keep vendors whose name matches or that have a store whose
    name / outlet code / city matches, and report up to MAX_MATCHES of those stores."""
    needle = (q or "").strip().lower()
    if len(needle) < 2:
        needle = ""
    # Digit-only matching is for phone-style searches only (no letters), so "es117" can't match on "117" alone.
    digits = "" if re.search(r"[a-z]", needle) else re.sub(r"\D", "", needle)  # lets "98765 43210" or "+91-98765…" still find a phone number
    groups: dict[str, list[Store]] = {}
    for s in _stores(db, user, is_admin=is_admin, partner=partner, region=region):
        groups.setdefault(_vendor_key(s), []).append(s)
    out = []
    for v, ss in groups.items():
        matches: list[Store] = []
        if needle:
            matches = [s for s in ss if _store_text(s).find(needle) >= 0 or (len(digits) >= 3 and digits in _store_digits(s))]
            vendor_hit = needle in v.lower() or (len(digits) >= 3 and digits in re.sub(r"\D", "", ss[0].vendor_number or ""))
            if not vendor_hit and not matches:
                continue
        out.append({
            "vendor": v, "stores": len(ss),
            "number": next((s.vendor_number for s in ss if s.vendor_number), None),
            "matches": [{"id": s.id, "name": s.name, "code": s.external_code} for s in matches[:MAX_MATCHES]],
            "match_total": len(matches),
        })
    return sorted(out, key=lambda x: x["vendor"].lower())


# --------------------------------------------------------------------------
# contact number(s)
# --------------------------------------------------------------------------

class _Contacts:
    """Phone number(s) printed on a card, cached per region / state."""

    def __init__(self, db: Session, org_id: uuid.UUID):
        self.db, self.org_id = db, org_id
        self._region: dict[tuple, list[str]] = {}
        self._state: dict[tuple, list[str]] = {}

    @staticmethod
    def _clean(p: str | None) -> str:
        return re.sub(r"\.0+$", "", (p or "").strip())

    def for_store(self, s: Store) -> str:
        slug = s.partner_organization.slug if s.partner_organization else None
        if assignment_service.is_employee_model(slug):          # Zepto: the employee the STATE is assigned to
            key = (s.partner_organization_id, (s.state or "").strip().lower())
            if key not in self._state:
                self._state[key] = [self._clean(p) for p in self.db.execute(
                    select(User.phone)
                    .join(StateAssignment, StateAssignment.assigned_user_id == User.id)
                    .where(StateAssignment.partner_organization_id == s.partner_organization_id,
                           func.lower(StateAssignment.state) == key[1], User.is_active.is_(True), User.phone.is_not(None))
                ).scalars() if self._clean(p)]
            phones = self._state[key][:1]
        else:                                                    # Blinkit: active employees of the store's REGION
            if s.region_id is None:
                return ""
            key = (s.partner_organization_id, s.region_id)
            if key not in self._region:
                self._region[key] = [self._clean(p) for p in self.db.execute(
                    select(User.phone).where(
                        User.organization_id == self.org_id, User.platform_organization_id == s.partner_organization_id,
                        User.region_id == s.region_id, User.is_active.is_(True), User.phone.is_not(None),
                    ).order_by(User.employee_code)
                ).scalars() if self._clean(p)]
            phones = self._region[key]
        return " / ".join(phones[:MAX_CONTACTS_ON_CARD])


# --------------------------------------------------------------------------
# PDF drawing (A4 portrait; sizes are the original CSS pixels x 0.75)
# --------------------------------------------------------------------------

PX = 0.75
W, H = 595.27, 841.89
CARD_W = 720 * PX          # 540 pt
LEFT = (W - CARD_W) / 2
TOP = H - 8 * 2.835        # 8 mm page margin


def _wrap(c, text: str, font: str, size: float, width: float, max_lines: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if c.stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,") + "…"
    return lines or [""]


LOGO_FILE = Path(__file__).resolve().parent.parent / "assets" / "watr-logo.png"


def logo_path() -> Path | None:
    """The logo printed on cards and PDFs: CARD_LOGO_PATH if set, else the bundled WaTR logo."""
    for p in (Path(settings.CARD_LOGO_PATH) if settings.CARD_LOGO_PATH else None, LOGO_FILE):
        if p is not None and p.is_file():
            return p
    return None


def draw_logo(c, x: float, y: float, w: float, h: float) -> bool:
    """Draw the logo inside the box (aspect ratio kept). Returns False if no logo file is available."""
    from reportlab.lib.utils import ImageReader

    p = logo_path()
    if p is None:
        return False
    try:
        c.drawImage(ImageReader(str(p)), x, y, w, h, preserveAspectRatio=True, anchor="c", mask="auto")
        return True
    except Exception:  # noqa: BLE001 — a bad image must never break the PDF
        return False


def _logo(c, x: float, y: float, w: float, h: float) -> None:
    if draw_logo(c, x, y, w, h):
        return
    c.setFillColorRGB(*C_MAIN)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(x + w / 2, y + h / 2 - 6, "WaTR")
    c.setFillColorRGB(*C_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(x + w / 2, y + h / 2 - 17, "VEE KAY AQUATECH")


def _qr_reader(url: str):
    import qrcode
    from reportlab.lib.utils import ImageReader

    qr = qrcode.QRCode(border=1, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _fmt_day(d: date) -> str:
    return f"{d.day}-{calendar.month_abbr[d.month]}-{d.year}"   # 2-Sep-2026


def _log_table(c, x: float, y_top: float, first_no: int, rows: int, with_total: bool, entries: list[tuple[date, int]] | None, total: int) -> float:
    """One of the two log tables. Returns the y of its bottom edge. Entries fill the rows in order."""
    cols = [24 * PX, 66 * PX, 80 * PX, 80 * PX, 98 * PX]       # '#', Date, Filled, Empty, Signature  (348 px)
    head_h, row_h = 28 * PX, 38 * PX
    heads = [("#",), ("Date",), ("Filled", "Bottle"), ("Empty", "Bottle"), ("Signature",)]
    tw = sum(cols)

    c.setFillColorRGB(*C_MAIN)
    c.setStrokeColorRGB(*C_MAIN)
    c.rect(x, y_top - head_h, tw, head_h, stroke=1, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 9 * PX)
    cx = x
    for w, h in zip(cols, heads):
        if len(h) == 1:
            c.drawCentredString(cx + w / 2, y_top - head_h / 2 - 2.4, h[0])
        else:
            c.drawCentredString(cx + w / 2, y_top - head_h / 2 + 1.2, h[0])
            c.drawCentredString(cx + w / 2, y_top - head_h / 2 - 6.3, h[1])
        cx += w

    y = y_top - head_h
    c.setStrokeColorRGB(*C_GRID)
    c.setLineWidth(0.75)
    for r in range(rows):
        e = entries[first_no - 1 + r] if entries and first_no - 1 + r < len(entries) else None
        c.rect(x, y - row_h, tw, row_h, stroke=1, fill=0)
        cx = x
        for w in cols[:-1]:
            cx += w
            c.line(cx, y - row_h, cx, y)
        base = y - row_h / 2 - 3
        c.setFillColorRGB(*C_MUTED)
        c.setFont("Helvetica", 9 * PX)
        c.drawCentredString(x + cols[0] / 2, base, str(first_no + r))
        if e:
            c.setFillColorRGB(*C_TEXT)
            c.setFont("Helvetica-Bold", 10.5 * PX)
            c.drawCentredString(x + cols[0] + cols[1] / 2, base, _fmt_day(e[0]))
            c.drawCentredString(x + cols[0] + cols[1] + cols[2] / 2, base, str(e[1]))
        y -= row_h

    if with_total:
        c.setFillColorRGB(*C_LIGHT)
        c.setStrokeColorRGB(*C_DARK)
        c.setLineWidth(1.5)
        c.rect(x, y - row_h, cols[0] + cols[1], row_h, stroke=1, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.rect(x + cols[0] + cols[1], y - row_h, tw - cols[0] - cols[1], row_h, stroke=1, fill=1)
        c.setFillColorRGB(*C_DARK)
        c.setFont("Helvetica-Bold", 10 * PX)
        c.drawCentredString(x + (cols[0] + cols[1]) / 2, y - row_h / 2 - 2.6, "TOTAL COUNT")
        if entries is not None:
            c.setFillColorRGB(*C_TEXT)
            c.setFont("Helvetica-Bold", 14 * PX)
            c.drawCentredString(x + cols[0] + cols[1] + (tw - cols[0] - cols[1]) / 2, y - row_h / 2 - 3.6, str(total))
        y -= row_h
    c.setLineWidth(1)
    return y


def _draw_card(c, s: Store, vendor: str, channel: str, month: date | None, entries: list[tuple[date, int]] | None, phone: str) -> None:
    x0, y = LEFT, TOP
    top_edge = y

    # ---- 1. month line (write-in on a blank card; the month on a card with entry) ----
    h = 34 * PX
    c.setFillColorRGB(*C_DARK)
    c.setFont("Helvetica-Bold", 13 * PX)
    prefix = "Month of  -  "
    c.drawString(x0 + 10 * PX, y - h / 2 - 3.4, prefix)
    px_ = x0 + 10 * PX + c.stringWidth(prefix, "Helvetica-Bold", 13 * PX)
    c.setFillColorRGB(*C_TEXT)
    c.drawString(px_, y - h / 2 - 3.4, month_label(month) if month else "______________________________")
    y -= h
    c.setStrokeColorRGB(*C_MAIN)
    c.setLineWidth(1.5)
    c.line(x0, y, x0 + CARD_W, y)

    # ---- 2. company band: name + email + contact (dark text on a light band) ----
    h = 58 * PX
    c.setFillColorRGB(*C_LIGHT)
    c.rect(x0, y - h, CARD_W, h, stroke=0, fill=1)
    c.setFillColorRGB(*C_DARK)
    c.setFont("Helvetica-Bold", 19 * PX)
    c.drawCentredString(x0 + CARD_W / 2, y - 25 * PX, settings.COMPANY_NAME)
    c.setFont("Helvetica-Bold", 11 * PX)
    parts = ([f"Email: {settings.COMPANY_EMAIL}"] if settings.COMPANY_EMAIL else []) + ([f"Contact: {phone}"] if phone else [])
    c.drawCentredString(x0 + CARD_W / 2, y - 46 * PX, "   |   ".join(parts))
    y -= h
    c.line(x0, y, x0 + CARD_W, y)

    # ---- 3. logo | title, channel, vendor | QR ----
    h = 134 * PX
    _logo(c, x0 + 10 * PX, y - h + 8 * PX, 150 * PX, h - 16 * PX)
    mid = x0 + 170 * PX + 396 * PX / 2
    c.setFillColorRGB(*C_DARK)
    c.setFont("Helvetica-Bold", 15 * PX)
    c.drawCentredString(mid, y - 44 * PX, "BOTTLE DELIVERY CARD")

    def kv(label: str, value: str, ypos: float) -> None:
        size = 12 * PX
        lw = c.stringWidth(label + " ", "Helvetica", size)
        total_w = lw + c.stringWidth(value, "Helvetica-Bold", size)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.setFont("Helvetica", size)
        c.drawString(mid - total_w / 2, ypos, label + " ")
        c.setFont("Helvetica-Bold", size)
        c.drawString(mid - total_w / 2 + lw, ypos, value)

    kv("Channel:", channel, y - 66 * PX)
    kv("Vendor:", _wrap(c, vendor, "Helvetica-Bold", 12 * PX, 330 * PX, 1)[0], y - 84 * PX)
    qs = 92 * PX
    qx = x0 + 170 * PX + 396 * PX + (150 * PX - qs) / 2
    c.drawImage(_qr_reader(qr_url(s.id)), qx, y - 12 * PX - qs, qs, qs)
    c.setFillColorRGB(0.27, 0.27, 0.27)
    c.setFont("Helvetica", 8 * PX)
    c.drawCentredString(qx + qs / 2, y - 12 * PX - qs - 9 * PX, "Scan to check bottle")
    c.drawCentredString(qx + qs / 2, y - 12 * PX - qs - 18 * PX, "count till date")
    y -= h
    c.setStrokeColorRGB(*C_MAIN)
    c.setLineWidth(3)
    c.line(x0, y, x0 + CARD_W, y)
    c.setLineWidth(1)

    # ---- 4. store details: two rows of three ----
    cw = CARD_W / 3

    def cell(cx: float, cy_top: float, rh: float, label: str, val: str | None, big: bool = False) -> None:
        c.setStrokeColorRGB(*C_BORDER)
        c.rect(cx, cy_top - rh, cw, rh, stroke=1, fill=0)
        c.setFillColorRGB(*C_MUTED)
        c.setFont("Helvetica", 8 * PX)
        c.drawString(cx + 8 * PX, cy_top - 13 * PX, label.upper())
        size = (15 if big else 12) * PX
        c.setFillColorRGB(*(C_DARK if big else C_TEXT))
        c.setFont("Helvetica-Bold", size)
        for i, ln in enumerate(_wrap(c, (val or "").strip() or "—", "Helvetica-Bold", size, cw - 16 * PX, 2)):
            c.drawString(cx + 8 * PX, cy_top - 28 * PX - i * (size + 2), ln)

    r1, r2 = 58 * PX, 46 * PX
    cell(x0, y, r1, "Store name", s.name)
    cell(x0 + cw, y, r1, "Store / Outlet ID", s.external_code, big=True)
    cell(x0 + 2 * cw, y, r1, "Entity", s.entity)
    y -= r1
    cell(x0, y, r2, "Region", s.region.name if s.region else None)
    cell(x0 + cw, y, r2, "State", s.state)
    cell(x0 + 2 * cw, y, r2, "City", s.city)
    y -= r2

    # ---- 5. the two log tables ----
    y -= 10 * PX
    total = sum(n for _, n in entries) if entries is not None else 0
    tx = x0 + 4 * PX
    bottom_l = _log_table(c, tx, y, 1, 15, False, entries, total)
    bottom_r = _log_table(c, tx + 348 * PX + 8 * PX, y, 16, 16, True, entries, total)
    bottom = min(bottom_l, bottom_r) - 6 * PX

    # outer border of the whole card
    c.setStrokeColorRGB(*C_MAIN)
    c.setLineWidth(1.5)
    c.rect(x0, bottom, CARD_W, top_edge - bottom, stroke=1, fill=0)
    c.setLineWidth(1)


def _entries_for(db: Session, store_ids: list[uuid.UUID], month: date) -> dict[uuid.UUID, list[tuple[date, int]]]:
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    out: dict[uuid.UUID, list[tuple[date, int]]] = {sid: [] for sid in store_ids}
    for sid, d, n in db.execute(
        select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count)
        .where(OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= month, OrderEntry.order_date <= end)
        .order_by(OrderEntry.order_date)
    ):
        out[sid].append((d, int(n)))
    return out


def _render(stores: list[Store], vendor: str, month: date | None, contacts: _Contacts, entries: dict | None) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"Monthwise virtual card - {vendor}" + (f" - {month_label(month)}" if month else ""))
    c.setAuthor(settings.COMPANY_NAME)
    for s in stores:
        platform = (s.partner_organization.name if s.partner_organization else "").upper()
        _draw_card(c, s, vendor, platform, month, entries[s.id] if entries is not None else None, contacts.for_store(s))
        c.showPage()
    c.save()
    return buf.getvalue()


def _safe_name(*parts: str) -> str:
    return re.sub(r"[^\w]+", "_", "_".join(p for p in parts if p)).strip("_")


def build_pdf(
    db: Session, user: User, *, is_admin: bool, partner: str | None, vendor: str | None,
    month: date | None, store_id: uuid.UUID | None = None, region: uuid.UUID | None = None,
) -> tuple[bytes, int, str]:
    """One PDF: a card per live store of the vendor (or a single store). month=None -> blank cards."""
    stores = _stores(db, user, is_admin=is_admin, partner=partner, region=region)
    if store_id is not None:
        stores = [s for s in stores if s.id == store_id]
        vendor = vendor or (_vendor_key(stores[0]) if stores else "")
    elif vendor:
        stores = [s for s in stores if _vendor_key(s).lower() == vendor.strip().lower()]
    if not stores:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No stores found for that selection.")
    if len(stores) > MAX_STORES_PER_PDF:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"That's more than {MAX_STORES_PER_PDF} stores — pick fewer.")
    stores.sort(key=lambda s: s.name.lower())
    entries = _entries_for(db, [s.id for s in stores], month) if month else None
    data = _render(stores, vendor or "", month, _Contacts(db, user.organization_id), entries)
    plat = stores[0].partner_organization.name if stores[0].partner_organization else ""
    name = _safe_name("Cards", f"Entry_{month:%Y-%m}" if month else "", plat, vendor or "store") + ".pdf"
    return data, len(stores), name


def build_zip(
    db: Session, user: User, *, is_admin: bool, partner: str | None, vendors: list[str], month: date | None,
    region: uuid.UUID | None = None,
) -> tuple[bytes, int, int, str]:
    """A ZIP holding one PDF per selected vendor. Returns (bytes, vendors, cards, filename)."""
    wanted = {v.strip().lower() for v in vendors if v and v.strip()}
    if not wanted:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one vendor.")
    groups: dict[str, list[Store]] = {}
    for s in _stores(db, user, is_admin=is_admin, partner=partner, region=region):
        if _vendor_key(s).lower() in wanted:
            groups.setdefault(_vendor_key(s), []).append(s)
    if not groups:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No stores found for those vendors.")
    total = sum(len(v) for v in groups.values())
    if total > MAX_STORES_PER_ZIP:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"That's {total} cards — the limit is {MAX_STORES_PER_ZIP} per ZIP. Pick fewer vendors.")

    all_stores = [s for v in groups.values() for s in v]
    entries = _entries_for(db, [s.id for s in all_stores], month) if month else None   # one query for every vendor
    contacts = _Contacts(db, user.organization_id)

    buf = io.BytesIO()
    used: set[str] = set()
    plat = (all_stores[0].partner_organization.name if partner and all_stores[0].partner_organization else "")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for vendor in sorted(groups, key=str.lower):
            stores = sorted(groups[vendor], key=lambda s: s.name.lower())
            pdf = _render(stores, vendor, month, contacts, entries)
            p0 = stores[0].partner_organization.name if stores[0].partner_organization else ""
            name = _safe_name("Cards", f"Entry_{month:%Y-%m}" if month else "", p0, vendor) + ".pdf"
            base, n = name, 1
            while name in used:
                n += 1
                name = base[:-4] + f"_{n}.pdf"
            used.add(name)
            zf.writestr(name, pdf)
    zip_name = _safe_name("Monthwise_cards", f"Entry_{month:%Y-%m}" if month else "Blank", plat) + ".zip"
    return buf.getvalue(), len(groups), total, zip_name
