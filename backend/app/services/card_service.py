"""
Vendor supply cards: one PDF per vendor, one A4 card per live store.

Each card: company band (logo, name, email, the responsible employee's phone),
store details, two daily log tables (days 1-15 and 16-31 + a total row) and a
signed QR code that opens a public page showing bottles supplied this month and
last month.

  - Admins (orders.correct) can print any store on a platform; employees only
    the stores assigned to them.
  - "Cards with entry" pre-fills the month's dates, filled-bottle counts and the
    total. Empty-bottle and signature columns always stay blank.
  - Contact number = phone of the region's employee (Blinkit) or of the
    employee the state is assigned to (Zepto).
  - The QR carries an HMAC signature, so only codes printed by us resolve.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.state_assignment import StateAssignment
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.services import assignment_service

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
NO_VENDOR = "No vendor"

# palette (mirrors the web app)
BRAND = (0.145, 0.349, 0.788)     # #2559c9
AQUA = (0.055, 0.557, 0.643)      # #0e8ea4
INK = (0.059, 0.086, 0.161)       # #0f1629
MUTED = (0.408, 0.443, 0.537)     # #687189
LINE = (0.784, 0.808, 0.863)      # #c8ced9
SOFT = (0.933, 0.941, 0.965)      # #eef0f6


def _today() -> date:
    return datetime.now(timezone.utc).date()


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


def public_count(db: Session, store_id: uuid.UUID, sig: str) -> dict:
    """Bottles supplied this month and last — no login, but only for a correctly signed store id."""
    if not verify_signature(store_id, sig):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This QR code isn't valid.")
    store = db.execute(
        select(Store).where(Store.id == store_id).options(joinedload(Store.partner_organization))
    ).unique().scalar_one_or_none()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This QR code isn't valid.")

    today = _today()
    this_start = today.replace(day=1)
    last_end = this_start.fromordinal(this_start.toordinal() - 1)
    last_start = last_end.replace(day=1)

    def totals(start: date, end: date) -> tuple[int, int]:
        row = db.execute(
            select(func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(OrderEntry.id)).where(
                OrderEntry.store_id == store.id, OrderEntry.order_date >= start, OrderEntry.order_date <= end
            )
        ).one()
        return int(row[0]), int(row[1])

    tb, te = totals(this_start, today)
    lb, le = totals(last_start, last_end)
    daily = db.execute(
        select(OrderEntry.order_date, OrderEntry.bottle_count)
        .where(OrderEntry.store_id == store.id, OrderEntry.order_date >= this_start, OrderEntry.order_date <= today)
        .order_by(OrderEntry.order_date)
    ).all()
    return {
        "store_name": store.name, "store_code": store.external_code,
        "platform": store.partner_organization.name if store.partner_organization else None,
        "city": store.city, "state": store.state,
        "this_month_label": f"{_MONTHS[today.month]} {today.year}", "this_month_bottles": tb, "this_month_entries": te,
        "last_month_label": f"{_MONTHS[last_start.month]} {last_start.year}", "last_month_bottles": lb, "last_month_entries": le,
        "daily": [{"date": d, "bottles": int(c)} for d, c in daily],
    }


# --------------------------------------------------------------------------
# store selection
# --------------------------------------------------------------------------

def _stores(db: Session, user: User, *, is_admin: bool, partner: str | None) -> list[Store]:
    if is_admin:
        stmt = (
            select(Store)
            .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
            .order_by(Store.name)
        )
        if partner:
            stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
        return list(db.execute(stmt).unique().scalars().all())
    rows = assignment_service.visible_stores(db, user)
    if partner:
        rows = [s for s in rows if s.partner_organization and s.partner_organization.slug == partner]
    return sorted(rows, key=lambda s: s.name.lower())


def _vendor_key(s: Store) -> str:
    return (s.vendor_name or "").strip() or NO_VENDOR


def list_vendors(db: Session, user: User, *, is_admin: bool, partner: str | None) -> list[dict]:
    groups: dict[str, list[Store]] = {}
    for s in _stores(db, user, is_admin=is_admin, partner=partner):
        groups.setdefault(_vendor_key(s), []).append(s)
    return sorted(
        ({"vendor": v, "stores": len(ss), "number": next((s.vendor_number for s in ss if s.vendor_number), None)}
         for v, ss in groups.items()),
        key=lambda x: (-x["stores"], x["vendor"].lower()),
    )


# --------------------------------------------------------------------------
# contact number
# --------------------------------------------------------------------------

class _Contacts:
    """Phone of the employee responsible for a store, cached per region / state."""

    def __init__(self, db: Session, org_id: uuid.UUID):
        self.db, self.org_id = db, org_id
        self._region: dict[tuple, str | None] = {}
        self._state: dict[tuple, str | None] = {}

    def for_store(self, s: Store) -> str | None:
        slug = s.partner_organization.slug if s.partner_organization else None
        if assignment_service.is_employee_model(slug):          # Zepto: state -> assigned employee
            key = (s.partner_organization_id, (s.state or "").strip().lower())
            if key not in self._state:
                row = self.db.execute(
                    select(User.phone)
                    .join(StateAssignment, StateAssignment.assigned_user_id == User.id)
                    .where(StateAssignment.partner_organization_id == s.partner_organization_id,
                           func.lower(StateAssignment.state) == key[1], User.phone.is_not(None))
                ).scalars().first()
                self._state[key] = row
            return self._state[key]
        if s.region_id is None:
            return None
        key = (s.partner_organization_id, s.region_id)          # Blinkit: region's employee
        if key not in self._region:
            self._region[key] = self.db.execute(
                select(User.phone).where(
                    User.organization_id == self.org_id, User.platform_organization_id == s.partner_organization_id,
                    User.region_id == s.region_id, User.is_active.is_(True), User.phone.is_not(None),
                ).order_by(User.employee_code)
            ).scalars().first()
        return self._region[key]


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

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
    return lines


def _draw_logo(c, x: float, y: float, size: float) -> None:
    from reportlab.lib.utils import ImageReader
    path = settings.CARD_LOGO_PATH
    if path:
        try:
            c.drawImage(ImageReader(path), x, y, size, size, preserveAspectRatio=True, mask="auto")
            return
        except Exception:  # noqa: BLE001 — fall back to the built-in mark
            pass
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(x, y, size, size, 9, stroke=0, fill=1)
    c.setFillColorRGB(*BRAND)
    c.setFont("Helvetica-Bold", size * 0.62)
    c.drawCentredString(x + size / 2, y + size * 0.22, "V")


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


def _draw_card(c, s: Store, month: date, entries: dict[int, int], with_entry: bool, phone: str | None) -> None:
    W, H = 595.27, 841.89
    M = 28.0
    days = calendar.monthrange(month.year, month.month)[1]

    # ---- company band ----
    band_h = 96.0
    c.setFillColorRGB(*BRAND)
    c.rect(0, H - band_h, W, band_h, stroke=0, fill=1)
    c.setFillColorRGB(*AQUA)
    c.rect(0, H - band_h - 4, W, 4, stroke=0, fill=1)
    _draw_logo(c, M, H - band_h + 24, 48)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(M + 60, H - 46, settings.COMPANY_NAME.upper())
    c.setFont("Helvetica", 10)
    c.drawString(M + 60, H - 62, settings.COMPANY_TAGLINE)
    c.setFont("Helvetica", 9.5)
    ry = H - 40
    if settings.COMPANY_EMAIL:
        c.drawRightString(W - M, ry, f"Email: {settings.COMPANY_EMAIL}")
        ry -= 15
    c.drawRightString(W - M, ry, f"Contact: {phone or '—'}")

    # ---- title ----
    y = H - band_h - 34
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(W / 2, y, "WATER SUPPLY LOG CARD")
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(W / 2, y - 16, f"{_MONTHS[month.month]} {month.year}")

    # ---- store details ----
    box_top = y - 30
    box_h = 104.0
    c.setFillColorRGB(*SOFT)
    c.setStrokeColorRGB(*LINE)
    c.roundRect(M, box_top - box_h, W - 2 * M, box_h, 8, stroke=1, fill=1)
    colw = (W - 2 * M) / 2
    left = [
        ("Store", s.name), ("Code", s.external_code),
        ("Platform", " · ".join(x for x in [s.partner_organization.name if s.partner_organization else None, s.entity] if x)),
        ("Location", ", ".join(x for x in [s.city, s.state] if x)),
    ]
    right = [
        ("POC", " · ".join(x for x in [s.poc_name, s.poc_number] if x)),
        ("Vendor", " · ".join(x for x in [s.vendor_name, s.vendor_number] if x)),
        ("Address", s.address or ""),
    ]

    def block(items, x0, y0, width):
        yy = y0
        for label, value in items:
            c.setFillColorRGB(*MUTED)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x0, yy, label.upper())
            c.setFillColorRGB(*INK)
            c.setFont("Helvetica", 10)
            lines = _wrap(c, value or "—", "Helvetica", 10, width - 62, 2 if label == "Address" else 1)
            for i, ln in enumerate(lines):
                c.drawString(x0 + 58, yy - i * 12, ln)
            yy -= 22 + (len(lines) - 1) * 12

    block(left, M + 14, box_top - 20, colw)
    block(right, M + colw + 6, box_top - 20, colw - 18)  # extra right padding so long addresses stay inside the box

    # ---- log tables ----
    row_h = 19.5
    tw = (W - 2 * M - 14) / 2
    cols = [0.27, 0.27, 0.22, 0.24]
    heads = ["DATE", "BOTTLES FILLED", "EMPTY", "SIGNATURE"]
    top = box_top - box_h - 18

    def table(x0: float, first_day: int, last_day: int, total_row: bool) -> None:
        c.setFillColorRGB(*BRAND)
        c.rect(x0, top - 22, tw, 22, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 7.6)
        cx = x0
        for w, h in zip(cols, heads):
            c.drawCentredString(cx + w * tw / 2, top - 14.5, h)
            cx += w * tw
        yy = top - 22
        n_rows = last_day - first_day + 1 + (1 if total_row else 0)
        for i in range(n_rows):
            is_total = total_row and i == n_rows - 1
            day = first_day + i
            yy_bottom = yy - row_h
            if is_total:
                c.setFillColorRGB(*SOFT)
                c.rect(x0, yy_bottom, tw, row_h, stroke=0, fill=1)
            c.setStrokeColorRGB(*LINE)
            c.rect(x0, yy_bottom, tw, row_h, stroke=1, fill=0)
            cx = x0
            for w in cols[:-1]:
                cx += w * tw
                c.line(cx, yy_bottom, cx, yy_bottom + row_h)
            base = yy_bottom + 6
            c.setFillColorRGB(*INK)
            if is_total:
                c.setFont("Helvetica-Bold", 9)
                c.drawCentredString(x0 + cols[0] * tw / 2, base, "TOTAL")
                if with_entry:
                    c.drawCentredString(x0 + cols[0] * tw + cols[1] * tw / 2, base, str(sum(entries.values())))
            elif day <= days:
                if with_entry:
                    c.setFont("Helvetica", 9)
                    c.drawCentredString(x0 + cols[0] * tw / 2, base, f"{day:02d}-{month.month:02d}-{month.year}")
                    if day in entries:
                        c.drawCentredString(x0 + cols[0] * tw + cols[1] * tw / 2, base, str(entries[day]))
            else:  # past month end: grey the row out
                c.setFillColorRGB(0.95, 0.95, 0.95)
                c.rect(x0 + 0.5, yy_bottom + 0.5, tw - 1, row_h - 1, stroke=0, fill=1)
            yy = yy_bottom

    table(M, 1, 15, False)
    table(M + tw + 14, 16, 31, True)

    # ---- footer: signatures + QR ----
    fy = top - 22 - 16 * row_h - row_h - 26
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.8)
    c.line(M, fy - 34, M + 150, fy - 34)
    c.line(M + 190, fy - 34, M + 340, fy - 34)
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawString(M, fy - 46, "Vendor signature")
    c.drawString(M + 190, fy - 46, "Store stamp")
    qs = 92.0
    c.drawImage(_qr_reader(qr_url(s.id)), W - M - qs, fy - qs + 14, qs, qs)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(W - M, fy - qs + 6, "Scan: bottles supplied")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(*LINE)
    c.drawString(M, 18, f"Generated {_today():%d %b %Y}  ·  {settings.COMPANY_NAME}")


def build_pdf(
    db: Session, user: User, *, is_admin: bool, partner: str | None, vendor: str | None,
    month: date, with_entry: bool, store_id: uuid.UUID | None = None,
) -> tuple[bytes, int]:
    from reportlab.pdfgen import canvas

    stores = _stores(db, user, is_admin=is_admin, partner=partner)
    if store_id is not None:
        stores = [s for s in stores if s.id == store_id]
    elif vendor:
        stores = [s for s in stores if _vendor_key(s).lower() == vendor.strip().lower()]
    if not stores:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No stores found for that selection.")
    if len(stores) > 400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That's more than 400 stores — pick a vendor or a platform first.")

    entries: dict[uuid.UUID, dict[int, int]] = {}
    if with_entry:
        end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
        for sid, d, n in db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count).where(
                OrderEntry.store_id.in_([s.id for s in stores]),
                OrderEntry.order_date >= month, OrderEntry.order_date <= end,
            )
        ):
            entries.setdefault(sid, {})[d.day] = int(n)

    contacts = _Contacts(db, user.organization_id)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595.27, 841.89))
    c.setTitle(f"Supply cards - {vendor or 'stores'} - {_MONTHS[month.month]} {month.year}")
    c.setAuthor(settings.COMPANY_NAME)
    for s in stores:
        _draw_card(c, s, month, entries.get(s.id, {}), with_entry, contacts.for_store(s))
        c.showPage()
    c.save()
    return buf.getvalue(), len(stores)
