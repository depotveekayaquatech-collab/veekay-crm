"""
Vendor / POC logins in one standard format, built from the store sheet's vendor and POC columns.

    vendor   <name>@supplier.com    password 123456
    POC      <name>@blinkit.com     password <name>@123

<name> is the person's name in lower case with everything but letters and digits removed ("Ajay Singh" -> ajaysingh).
Two different people can share a name: when a name carries more than one phone number, each number becomes its own
account with the last four digits added (sanjay8435@supplier.com), so no two people ever share a login. Placeholder
names ("#N/A", "NA", ...) are skipped. Everything here is pure except `build_accounts` reading stores and `apply`.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.external_account import AccountKind, ExternalAccount, ExternalAccountStore
from app.models.organization import Organization
from app.models.store import Store

VENDOR_DOMAIN = "supplier.com"
POC_DOMAIN = "blinkit.com"
VENDOR_PASSWORD = "123456"
JUNK = {"na", "nan", "none", "nil", "null", "tbd", "notavailable", "unknown", "no", "nill"}


def local_part(name: str | None) -> str:
    """'Ajay Singh' -> 'ajaysingh'. Empty string when nothing usable is left."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def primary_number(text: str | None) -> str | None:
    """The first 10-digit mobile number in the text ('9035454807 / 9108505863', '+91 90354 54807' ...)."""
    cleaned = re.sub(r"[\s\-().]", "", text or "")
    m = re.search(r"(?<!\d)(?:\+?91)?(\d{10})(?!\d)", cleaned)
    return m.group(1) if m else None


def poc_password(local: str) -> str:
    return f"{local}@123"


@dataclass
class Person:
    kind: str
    email: str
    password: str
    name: str
    phones: list[str]
    platforms: set[str]
    store_ids: set[uuid.UUID] = field(default_factory=set)


@dataclass
class Plan:
    people: list[Person]
    skipped: list[str]                  # placeholder / unusable names
    split_names: dict[str, int]         # name -> how many different people share it


def _display_name(spellings: Counter) -> str:
    return " ".join(spellings.most_common(1)[0][0].split())


def plan_for(rows: list[dict], kind: str) -> tuple[list[Person], list[str], dict[str, int]]:
    """rows: {name, number, store_id, platform}. Groups the rows into accounts (see module docstring)."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    skipped: list[str] = []
    for r in rows:
        name = " ".join((r["name"] or "").split())
        if not name:
            continue
        key = local_part(name)
        if len(key) < 2 or key in JUNK:
            skipped.append(name)
            continue
        by_name[key].append({**r, "name": name, "phone": primary_number(r["number"])})

    domain = VENDOR_DOMAIN if kind == AccountKind.VENDOR else POC_DOMAIN
    people: list[Person] = []
    split: dict[str, int] = {}
    for key, group in sorted(by_name.items()):
        numbers = Counter(r["phone"] for r in group if r["phone"])
        if len(numbers) <= 1:
            parts = [(key, group)]
        else:
            # Different phone numbers = different people with the same name: one account per number.
            split[key] = len(numbers)
            last4 = Counter(n[-4:] for n in numbers)
            top = numbers.most_common(1)[0][0]
            buckets: dict[str, list[dict]] = defaultdict(list)
            for r in group:
                buckets[r["phone"] or top].append(r)      # a row without a number goes with the busiest person
            parts = [(f"{key}{n[-4:] if last4[n[-4:]] == 1 else n}", rows_) for n, rows_ in sorted(buckets.items())]
        for local, rows_ in parts:
            phones = sorted({r["phone"] for r in rows_ if r["phone"]})
            raw_numbers = sorted({(r["number"] or "").strip() for r in rows_ if (r["number"] or "").strip()})
            people.append(Person(
                kind=kind, email=f"{local}@{domain}",
                password=VENDOR_PASSWORD if kind == AccountKind.VENDOR else poc_password(local),
                name=_display_name(Counter(r["name"] for r in rows_)),
                phones=phones or raw_numbers[:1],
                platforms={r["platform"] for r in rows_}, store_ids={r["store_id"] for r in rows_},
            ))
    return people, skipped, split


def build_plan(db: Session, platforms: set[str] | None) -> tuple[Plan, Plan]:
    """(vendors, pocs) for the stores of the chosen platforms (None = every platform)."""
    stmt = select(Store.id, Store.vendor_name, Store.vendor_number, Store.poc_name, Store.poc_number, Organization.slug).join(
        Organization, Organization.id == Store.partner_organization_id)
    if platforms:
        stmt = stmt.where(Organization.slug.in_(platforms))
    data = db.execute(stmt).all()
    out = []
    for kind, name_i, num_i in ((AccountKind.VENDOR, 1, 2), (AccountKind.POC, 3, 4)):
        people, skipped, split = plan_for(
            [{"name": r[name_i], "number": r[num_i], "store_id": r[0], "platform": r[5]} for r in data], kind)
        out.append(Plan(people, skipped, split))
    return out[0], out[1]


def check_unique(plans: list[Plan]) -> None:
    seen = Counter(p.email for plan in plans for p in plan.people)
    dupes = [e for e, n in seen.items() if n > 1]
    if dupes:
        raise ValueError(f"Duplicate logins would be created: {dupes[:5]}")


def apply(db: Session, org_id: uuid.UUID, plans: list[Plan]) -> dict[str, int]:
    """Creates the missing accounts and refreshes every account's store list. Existing accounts keep their password."""
    check_unique(plans)
    existing = {a.email: a for a in db.execute(select(ExternalAccount).where(ExternalAccount.organization_id == org_id)).scalars()}
    created = updated = 0
    for plan in plans:
        for p in plan.people:
            acct = existing.get(p.email)
            if acct is None:
                acct = ExternalAccount(
                    organization_id=org_id, kind=p.kind, email=p.email, full_name=p.name, password_hash=hash_password(p.password),
                    must_change_password=True,
                )
                db.add(acct)
                db.flush()
                created += 1
            else:
                updated += 1
            acct.full_name = p.name
            acct.phone = " / ".join(p.phones) or None
            acct.platforms = sorted(p.platforms)
            acct.store_count = len(p.store_ids)
            have = set(db.execute(select(ExternalAccountStore.store_id).where(ExternalAccountStore.account_id == acct.id)).scalars())
            for sid in p.store_ids - have:
                db.add(ExternalAccountStore(account_id=acct.id, store_id=sid))
            for sid in have - p.store_ids:
                db.query(ExternalAccountStore).filter_by(account_id=acct.id, store_id=sid).delete()
    db.commit()
    return {"created": created, "updated": updated}
