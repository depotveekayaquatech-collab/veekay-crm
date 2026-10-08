"""Realistic volume: 1,500 stores, ~70 employees, 90 days of orders, cash purchases, tickets, compliance rows, audit logs."""
import os
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
random.seed(7)

from sqlalchemy import insert, text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.cash_purchase import CashPurchase  # noqa: E402
from app.models.compliance_document import ComplianceDocument  # noqa: E402
from app.models.order_entry import OrderEntry  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.permission import Permission  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.state_assignment import StateAssignment  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.models.ticket import Ticket  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.user_permission import UserPermission  # noqa: E402

db = SessionLocal()
t0 = time.time()
org = db.query(Organization).filter_by(slug="veekay").one()
blinkit = db.query(Organization).filter_by(slug="blinkit").one()
zepto = db.query(Organization).filter_by(slug="zepto").one()
regions = {r.code: r for r in db.query(Region)}
emp_role = db.query(Role).filter_by(code="employee").one()
PW = hash_password("Load-Test-Pass-1")           # one real bcrypt hash, reused (hashing cost is measured at login)

# demo stores from the seed would skew the numbers; drop them and their entries
for t in ("order_entries", "state_assignments", "stores"):
    db.execute(text(f"DELETE FROM {t}"))
db.commit()

N_BLINKIT, N_ZEPTO = 900, 600
BL_STATES = {"NORTH": ["Delhi", "Haryana", "Punjab"], "WEST": ["Maharashtra", "Gujarat"], "SOUTH": ["Karnataka", "Tamil Nadu", "Telangana"]}
ZP_STATES = ["Maharashtra", "Karnataka", "Delhi", "Gujarat", "Telangana", "Tamil Nadu", "West Bengal", "Rajasthan", "Uttar Pradesh", "Kerala"]
CITIES = ["Bhiwandi", "Pune", "Mumbai", "Thane", "Gurugram", "Noida", "Bengaluru", "Hyderabad", "Chennai", "Ahmedabad", "Surat", "Jaipur", "Kochi", "Kolkata", "Lucknow"]
VENDORS = [f"Vendor {i:03d} Aqua" for i in range(1, 121)]
stores = []
for i in range(N_BLINKIT):
    code = list(regions)[i % 3] if False else ["NORTH", "WEST", "SOUTH"][i % 3]
    st = random.choice(BL_STATES[code])
    stores.append(dict(id=uuid.uuid4(), organization_id=org.id, partner_organization_id=blinkit.id, region_id=regions[code].id,
                       name=f"Blinkit - {random.choice(CITIES)} {random.choice(['Sector', 'Phase', 'Nagar', 'Market'])} {i + 1}",
                       external_code=f"BLK-LD-{i + 1:04d}", status="LIVE", state=st, city=random.choice(CITIES), entity="BCPL",
                       poc_name="Store Manager", poc_number=f"98{random.randint(10000000, 99999999)}",
                       vendor_name=random.choice(VENDORS), vendor_number=f"97{random.randint(10000000, 99999999)}"))
for i in range(N_ZEPTO):
    st = ZP_STATES[i % len(ZP_STATES)]
    stores.append(dict(id=uuid.uuid4(), organization_id=org.id, partner_organization_id=zepto.id, region_id=None,
                       name=f"Zepto - {random.choice(CITIES)} {random.choice(['Dark Store', 'Hub', 'Mart'])} {i + 1}",
                       external_code=f"ZEP-LD-{i + 1:04d}", status="LIVE", state=st, city=random.choice(CITIES),
                       poc_name="Store Manager", poc_number=f"98{random.randint(10000000, 99999999)}",
                       vendor_name=random.choice(VENDORS), vendor_number=f"97{random.randint(10000000, 99999999)}"))
db.execute(insert(Store), stores); db.commit()
print(f"stores {len(stores)}  ({time.time() - t0:.1f}s)")

# employees: 60 Blinkit (region model, 20 per region), 10 Zepto (one state each)
users, roles, perms_rows, assigns = [], [], [], []
grant_codes = ["orders.view", "orders.mark", "compliance.upload", "tickets.view", "tickets.create", "cash.add"]
perm_ids = {p.code: p.id for p in db.query(Permission).filter(Permission.code.in_(grant_codes))}
emp_meta = []
for i in range(60):
    rc = ["NORTH", "WEST", "SOUTH"][i % 3]
    emp_meta.append(("EMPB%03d" % (i + 1), blinkit.id, regions[rc].id, None))
for i in range(10):
    emp_meta.append(("EMPZ%03d" % (i + 1), zepto.id, None, ZP_STATES[i]))
for code, plat, reg, state in emp_meta:
    uid = uuid.uuid4()
    users.append(dict(id=uid, organization_id=org.id, employee_code=code, full_name=f"Load {code}", password_hash=PW, status="active",
                      must_change_password=False, platform_organization_id=plat, region_id=reg, is_active=True))
    roles.append(dict(id=uuid.uuid4(), user_id=uid, role_id=emp_role.id))
    for c in grant_codes:
        perms_rows.append(dict(id=uuid.uuid4(), user_id=uid, permission_id=perm_ids[c]))
    if state:
        assigns.append(dict(id=uuid.uuid4(), organization_id=org.id, partner_organization_id=zepto.id, state=state, assigned_user_id=uid))
db.execute(insert(User), users); db.execute(insert(UserRole), roles); db.execute(insert(UserPermission), perms_rows)
db.execute(insert(StateAssignment), assigns); db.commit()
user_ids = [u["id"] for u in users]
print(f"employees {len(users)} ({time.time() - t0:.1f}s)")

# 90 days of order entries (today is left empty so employees can mark it)
today = date.today()
rows, total = [], 0
for s in stores:
    for d in range(1, 91):
        rows.append(dict(id=uuid.uuid4(), organization_id=org.id, store_id=s["id"], order_date=today - timedelta(days=d),
                         bottle_count=random.randint(4, 60), cash_adjustment=0, source="employee", marked_by_user_id=random.choice(user_ids)))
    if len(rows) >= 30000:
        db.execute(insert(OrderEntry), rows); db.commit(); total += len(rows); rows = []
if rows:
    db.execute(insert(OrderEntry), rows); db.commit(); total += len(rows)
print(f"order entries {total} ({time.time() - t0:.1f}s)")

# cash purchases (no proof files: metadata volume only), tickets, compliance rows, audit logs
emp = db.query(User).filter_by(employee_code="EMP001").first()
cp = []
for i in range(4000):
    st = random.random() < 0.7
    cp.append(dict(id=uuid.uuid4(), organization_id=org.id, kind="STORE" if st else "OFFICE", store_id=random.choice(stores)["id"] if st else None,
                   purchase_date=today - timedelta(days=random.randint(0, 80)), category=random.choice(["SUPPLY_DELAYED", "VENDOR_NOT_RESPONDING", "EMERGENCY_REQUIREMENT"]) if st else random.choice(["MILK", "STATIONERY", "CLEANING"]),
                   amount=random.choice([80, 120, 150, 240, 300, 500]), created_by_user_id=random.choice(user_ids)))
db.execute(insert(CashPurchase), cp)
tk = []
for i in range(2000):
    s = random.choice(stores)
    tk.append(dict(id=uuid.uuid4(), organization_id=org.id, store_id=s["id"], partner_organization_id=s["partner_organization_id"],
                   category=random.choice(["LATE_DELIVERY", "NO_DELIVERY", "SHORT_SUPPLY", "QUALITY", "OTHER"]), priority="MEDIUM",
                   status=random.choice(["OPEN", "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]), title="Load ticket", source="app",
                   created_by_user_id=random.choice(user_ids)))
db.execute(insert(Ticket), tk)
cm = []
for s in stores:
    for back in (0, 1):
        m = (today.replace(day=1) - timedelta(days=30 * back)).replace(day=1)
        cm.append(dict(id=uuid.uuid4(), organization_id=org.id, store_id=s["id"], month=m, kind="card", file_key=f"load/{s['id']}/{m:%Y-%m}.pdf",
                       file_name="card.pdf", content_type="application/pdf", size_bytes=250000, storage_backend="local", uploaded_by_user_id=random.choice(user_ids)))
db.execute(insert(ComplianceDocument), cm)
al = [dict(id=uuid.uuid4(), user_id=random.choice(user_ids), organization_id=org.id, action=random.choice(["order.marked", "order.corrected", "cash_purchase.created"]),
           entity_type="order_entry", entity_id=str(uuid.uuid4()), metadata_json={"n": i}, created_at=datetime.now(timezone.utc) - timedelta(minutes=i), updated_at=datetime.now(timezone.utc)) for i in range(60000)]
for k in range(0, len(al), 20000):
    db.execute(insert(AuditLog), al[k:k + 20000])
db.commit()
db.execute(text("ANALYZE")); db.commit()
for t in ("stores", "users", "order_entries", "cash_purchases", "tickets", "compliance_documents", "audit_logs"):
    print(f"  {t:22} {db.execute(text(f'select count(*) from {t}')).scalar():>8}")
print(f"database size: {db.execute(text('select pg_size_pretty(pg_database_size(current_database()))')).scalar()}  total {time.time() - t0:.0f}s")
