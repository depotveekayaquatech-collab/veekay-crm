"""
Database seed.

    python scripts/seed.py

In development (ENVIRONMENT != production) it also creates demo users
(ADMIN001 / EMP001 / EMP002 with a known password), demo stores and sample
entries. In PRODUCTION it creates none of that — only the organization,
platforms, permissions, roles and regions — so no account with a known
password ever exists. To get the first admin into a fresh production
database, set BOOTSTRAP_ADMIN_PASSWORD: ADMIN001 is created with it (once)
and must choose a new password at first sign-in.

Original description:

    python scripts/seed.py

Idempotent — safe to re-run. Creates the Veekay org + Blinkit/Zepto
platforms, roles + permissions, an admin and two field employees
(one region-model on Blinkit, one state-model on Zepto), regions,
stores with LIVE/PENDING status, a Zepto state assignment, and a few
bottle-count entries for today/yesterday.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.permission import Permission, RolePermission
from app.models.region import Region
from app.models.role import Role
from app.models.state_assignment import StateAssignment
from app.models.store import Store
from app.core.roles import RESERVED_PERMISSIONS
from app.models.user import User, UserRole, UserStatus

PERMISSIONS = [
    ("orders.view", "View order calendars"),
    ("orders.mark", "Mark bottle counts"),
    ("orders.correct", "Correct or clear any entry"),
    ("orders.overview", "View the admin daily overview"),
    ("stores.view", "View stores"),
    ("stores.manage", "Create and edit stores"),
    ("regions.view", "View regions"),
    ("regions.manage", "Create and edit regions"),
    ("employees.view", "View employees"),
    ("employees.create", "Create employees and set permissions"),
    ("employees.update", "Edit employees"),
    ("employees.deactivate", "Deactivate employees"),
    ("assignments.manage", "Assign regions and states to employees"),
    ("activity.view", "View the activity log"),
    ("compliance.upload", "Upload compliance cards and bills for your own stores"),
    ("compliance.manage", "Upload, view and remove cards and bills for any store"),
    ("accounts.view", "Accountant dashboard: bill due alerts, search, view and download documents"),
    ("accounts.clear", "Mark bills as cleared"),
    ("attendance.view", "View everyone's attendance (sign-in / sign-out times and location)"),
    ("attendance.manage", "Set the office locations used to recognise 'at the office'"),
    ("leave.review", "Approve or reject leave requests"),
    ("reports.delivery", "Download delivery reports (partner accounts)"),
    ("cash.view", "See every cash purchase and download the sheet"),
    ("cash.add", "Record cash purchases (you see your own entries)"),
    ("sheets.sync", "Sheet sync and bulk sheet / file uploads of stores and orders (developer only)"),
    ("cash.adjust", "Cash-purchase adjustments to the order sheet and their history (developer only)"),
    ("bottles.view", "View bottle QR codes, their scan history and the overdue / lost list"),
    ("bottles.scan", "Scan bottle QR codes in and out of stores"),
    ("bottles.manage", "Generate bottle QR codes, replace damaged ones and retire bottles"),
    ("bottles.delete", "Permanently delete bottle QR codes so they can never be used again (developer only)"),
    ("logins.view", "View and export the vendor / POC logins prepared for the mobile app"),
    ("cards.sheet", "Cards from an uploaded sheet, behind an access code (developer only for now)"),
    ("tickets.view", "View tickets for your stores"),
    ("tickets.create", "Raise tickets"),
    ("tickets.manage", "Manage every ticket: assign, change status, see all regions and insights"),
]

ADMIN_PERMISSIONS = [code for code, _ in PERMISSIONS if code not in RESERVED_PERMISSIONS]
# The 'employee' role grants nothing on its own — every field employee's
# access is the exact set of per-user permission checkboxes an admin ticks
# (so an admin can also take capability away, not only add it).
EMPLOYEE_PERMISSIONS: list[str] = []
DEFAULT_EMPLOYEE_GRANTS = ["orders.view", "orders.mark", "compliance.upload", "tickets.view", "tickets.create", "cash.add"]
ACCOUNTANT_PERMISSIONS = ["accounts.view", "accounts.clear", "cash.view", "cash.add"]

SEED_PASSWORD = "Pass@123"

REGIONS = [("North", "NORTH"), ("West", "WEST"), ("South", "SOUTH")]

# (name, code, partner, region_code, state, city, status)
STORES = [
    ("Blinkit — Saket", "BLK-4821", "blinkit", "NORTH", "Delhi", "New Delhi", "LIVE"),
    ("Blinkit — Rohini", "BLK-4830", "blinkit", "NORTH", "Delhi", "New Delhi", "LIVE"),
    ("Blinkit — Gurugram", "BLK-4901", "blinkit", "NORTH", "Haryana", "Gurugram", "LIVE"),
    ("Blinkit — Andheri", "BLK-5093", "blinkit", "WEST", "Maharashtra", "Mumbai", "LIVE"),
    ("Blinkit — Pune Kothrud", "BLK-5140", "blinkit", "WEST", "Maharashtra", "Pune", "PENDING"),
    ("Zepto — Koramangala", "ZEP-1187", "zepto", "SOUTH", "Karnataka", "Bengaluru", "LIVE"),
    ("Zepto — Indiranagar", "ZEP-1190", "zepto", "SOUTH", "Karnataka", "Bengaluru", "LIVE"),
    ("Zepto — HITEC City", "ZEP-1250", "zepto", "SOUTH", "Telangana", "Hyderabad", "LIVE"),
]


def main() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug="veekay").first()
        if org is None:
            org = Organization(slug="veekay", name="Veekay Aquatech", kind=OrganizationKind.INTERNAL.value)
            db.add(org)
            db.flush()

        partners = {}
        for slug, name in [("blinkit", "Blinkit"), ("zepto", "Zepto")]:
            p = db.query(Organization).filter_by(slug=slug).first()
            if p is None:
                p = Organization(slug=slug, name=name, kind=OrganizationKind.PARTNER.value)
                db.add(p)
                db.flush()
            partners[slug] = p

        perms = {}
        for code, desc in PERMISSIONS:
            perm = db.query(Permission).filter_by(code=code).first()
            if perm is None:
                perm = Permission(code=code, description=desc)
                db.add(perm)
                db.flush()
            perms[code] = perm

        def ensure_role(code, name, codes):
            role = db.query(Role).filter_by(code=code).first()
            if role is None:
                role = Role(code=code, name=name)
                db.add(role)
                db.flush()
            have = {rp.permission_id for rp in role.role_permissions}
            for c in codes:
                if perms[c].id not in have:
                    db.add(RolePermission(role_id=role.id, permission_id=perms[c].id))
            return role

        admin_role = ensure_role("admin", "Admin", ADMIN_PERMISSIONS)
        employee_role = ensure_role("employee", "Employee", EMPLOYEE_PERMISSIONS)
        ensure_role("accountant", "Accountant", ACCOUNTANT_PERMISSIONS)
        ensure_role("partner", "Partner account", [])
        ensure_role("manager", "Custom admin", [])
        ensure_role("developer", "Developer", sorted(RESERVED_PERMISSIONS))
        db.flush()

        regions = {}
        for name, code in REGIONS:
            r = db.query(Region).filter_by(organization_id=org.id, code=code).first()
            if r is None:
                r = Region(organization_id=org.id, name=name, code=code)
                db.add(r)
                db.flush()
            regions[code] = r

        demo = settings.ENVIRONMENT.strip().lower() != "production"

        stores = {}
        for name, code, pslug, rcode, state, city, st in (STORES if demo else []):
            s = db.query(Store).filter_by(partner_organization_id=partners[pslug].id, external_code=code).first()
            if s is None:
                s = Store(
                    organization_id=org.id,
                    partner_organization_id=partners[pslug].id,
                    region_id=regions[rcode].id,
                    name=name, external_code=code, state=state, city=city,
                    status=st, vendor_name="Local Vendor", vendor_number="9000000000",
                    poc_name="Store Manager", poc_number="9111111111",
                )
                db.add(s)
                db.flush()
            stores[code] = s

        def ensure_user(code, name, role, *, platform=None, region=None, password=None, must_change=False):
            u = db.query(User).filter_by(organization_id=org.id, employee_code=code).first()
            if u is None:
                u = User(
                    organization_id=org.id, employee_code=code, full_name=name,
                    password_hash=hash_password(password or SEED_PASSWORD), status=UserStatus.ACTIVE.value,
                    must_change_password=must_change,
                )
                db.add(u)
                db.flush()
            if platform is not None:
                u.platform_organization_id = platform.id
            if region is not None:
                u.region_id = region.id
            if not db.query(UserRole).filter_by(user_id=u.id, role_id=role.id).first():
                db.add(UserRole(user_id=u.id, role_id=role.id))
            return u

        from app.models.user_permission import UserPermission

        def grant(user, codes):
            have = {up.permission_id for up in db.query(UserPermission).filter_by(user_id=user.id)}
            for c in codes:
                if perms[c].id not in have:
                    db.add(UserPermission(user_id=user.id, permission_id=perms[c].id))

        if demo:
            ensure_user("ADMIN001", "Admin User", admin_role)
            # Demo only: this login is an admin AND a developer (every admin feature + the Data sync tab).
            # The developer role on its own stays strict; see scripts/create_developer.py.
            demo_dev = ensure_user("DEV001", "Developer (demo)", admin_role)
            ensure_user("DEV001", "Developer (demo)", db.query(Role).filter_by(code="developer").one())
            blinkit_emp = ensure_user(
                "EMP001", "Ravi Kumar (Blinkit / North)", employee_role,
                platform=partners["blinkit"], region=regions["NORTH"],
            )
            zepto_emp = ensure_user(
                "EMP002", "Sana Sheikh (Zepto)", employee_role, platform=partners["zepto"],
            )
            db.flush()
            grant(blinkit_emp, DEFAULT_EMPLOYEE_GRANTS)
            grant(zepto_emp, DEFAULT_EMPLOYEE_GRANTS)

            # Zepto: assign Karnataka to the Zepto employee (Telangana stays unassigned).
            if not db.query(StateAssignment).filter_by(
                partner_organization_id=partners["zepto"].id, state="Karnataka"
            ).first():
                db.add(StateAssignment(
                    organization_id=org.id, partner_organization_id=partners["zepto"].id,
                    state="Karnataka", assigned_user_id=zepto_emp.id,
                ))

            # A few bottle-count entries.
            today = date.today()
            yesterday = today - timedelta(days=1)
            samples = [
                ("BLK-4821", yesterday, 24, EntrySource.EMPLOYEE, blinkit_emp),
                ("BLK-4830", yesterday, 12, EntrySource.EMPLOYEE, blinkit_emp),
                ("BLK-4821", today, 30, EntrySource.EMPLOYEE, blinkit_emp),
                ("ZEP-1187", yesterday, 18, EntrySource.EMPLOYEE, zepto_emp),
                ("ZEP-1190", today, 0, EntrySource.EMPLOYEE, zepto_emp),
            ]
            for code, d, count, src, emp in samples:
                s = stores[code]
                if db.query(OrderEntry).filter_by(store_id=s.id, order_date=d).first():
                    continue
                db.add(OrderEntry(
                    organization_id=org.id, store_id=s.id, order_date=d,
                    bottle_count=count, source=src.value, marked_by_user_id=emp.id,
                ))


        else:
            boot = settings.BOOTSTRAP_ADMIN_PASSWORD
            if boot:
                exists = db.query(User).filter_by(organization_id=org.id, employee_code="ADMIN001").first()
                if exists is None:
                    ensure_user("ADMIN001", "Administrator", admin_role, password=boot, must_change=True)
                    print("Created ADMIN001 from BOOTSTRAP_ADMIN_PASSWORD (must change it at first sign-in).")

        db.commit()
        print("Seeded (production: no demo users, stores or entries)." if not demo else "Seeded Phase 4.")
        if demo:
            print("  ADMIN001 / Pass@123  (admin)")
            print("  DEV001   / Pass@123  (demo: admin + developer, so every admin feature plus Data sync)")
            print("  EMP001   / Pass@123  (Blinkit, North region)")
            print("  EMP002   / Pass@123  (Zepto, Karnataka state)")
            print("Login with organization='veekay'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
