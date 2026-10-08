"""
Test harness.

The suite runs against a REAL PostgreSQL database (the models use Postgres types and functions), but never
the development one: a throwaway database named `veekay_test` is dropped, recreated, migrated and seeded
once per run. Point it at another server with TEST_DATABASE_URL (CI does).

Environment for the app is set here, BEFORE any app module is imported.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _test_db_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND / ".env").get("DATABASE_URL") or \
        "postgresql+psycopg://postgres:postgres@localhost:5432/veekay_dev"
    return re.sub(r"/[^/?]+(\?.*)?$", r"/veekay_test", base)


TEST_DB_URL = _test_db_url()
_STORAGE_DIR = tempfile.mkdtemp(prefix="veekay-test-storage-")

os.environ.update({
    "DATABASE_URL": TEST_DB_URL,
    "JWT_SECRET_KEY": "test-secret-key-not-for-production-0123456789",
    "ENVIRONMENT": "test",
    "DEBUG": "false",
    "BCRYPT_ROUNDS": "4",
    "RATE_LIMIT_ENABLED": "false",       # individual tests switch it on
    "LOG_LEVEL": "WARNING",
    "UPLOAD_DIR": _STORAGE_DIR,
    "STORAGE_BACKEND": "local",
    "PUBLIC_APP_URL": "http://testserver",
    "CARDS_FIRST_MONTH": "2026-09",
    "COMPLIANCE_EARLIEST_MONTH": "2026-06",
    "SENTRY_DSN": "",
    "BOOTSTRAP_ADMIN_PASSWORD": "",
})
for k in ("STORE_SYNC_SHEETS",):
    os.environ.pop(k, None)


def _admin_dsn() -> tuple[str, str]:
    plain = TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://")
    name = plain.rsplit("/", 1)[-1].split("?")[0]
    return re.sub(r"/[^/?]+(\?.*)?$", "/postgres", plain), name


def pytest_sessionstart(session) -> None:
    admin_dsn, name = _admin_dsn()
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    env = {**os.environ}
    for cmd in (["-m", "alembic", "upgrade", "head"], ["scripts/seed.py"]):
        r = subprocess.run([sys.executable, *cmd], cwd=BACKEND, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"test database setup failed ({cmd}):\n{r.stdout}\n{r.stderr}")


def pytest_sessionfinish(session, exitstatus) -> None:
    shutil.rmtree(_STORAGE_DIR, ignore_errors=True)


# ---- imports that need the environment above ----
from fastapi.testclient import TestClient  # noqa: E402

from app.core import storage  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.middleware import rate_windows  # noqa: E402
from app.core.ratelimit import login_failures  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.attendance import AttendanceRecord, AttendanceSession, LeaveRequest, Office  # noqa: E402
from app.models.compliance_document import ComplianceDocument  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.refresh_session import RefreshSession  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.store import Store  # noqa: E402
from app.models.ticket import Ticket  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.user_permission import UserPermission  # noqa: E402
from app.models.permission import Permission  # noqa: E402

DEMO_PASSWORD = "Pass@123"          # the seeded demo users (ADMIN001, EMP001 Blinkit/North, EMP002 Zepto/Karnataka)
API = settings.API_V1_PREFIX


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def _clean_state():
    """Every test starts with empty throttles and ends with no leftovers from the tables it may touch."""
    rate_windows.reset()
    login_failures.reset()
    storage.reset_backend()
    yield
    s = SessionLocal()
    try:
        for model in (Ticket, AttendanceRecord, LeaveRequest, AttendanceSession, ComplianceDocument, RefreshSession, Office):
            s.query(model).delete()
        s.commit()
    finally:
        s.close()
    shutil.rmtree(_STORAGE_DIR, ignore_errors=True)
    Path(_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# helpers used across the suite
# --------------------------------------------------------------------------

def login(client: TestClient, code: str, password: str = DEMO_PASSWORD, **extra):
    return client.post(f"{API}/auth/login", json={"employee_code": code, "password": password, **extra})


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client):
    r = login(client, "ADMIN001")
    assert r.status_code == 200, r.text
    return auth(r.json()["access_token"])


@pytest.fixture()
def dev(client, db):
    """A strict developer account (sheet sync / bulk upload only), made the way production makes one."""
    from scripts.create_developer import make_developer

    code = f"TD{uuid.uuid4().hex[:6].upper()}"
    pw = "Dev-Pass-2026x"
    user = make_developer(db, code, "Test Developer", pw)
    r = login(client, code, pw)
    assert r.status_code == 200, r.text
    yield auth(r.json()["access_token"])
    for model in (RefreshSession, UserRole):
        db.query(model).filter(model.user_id == user.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.commit()


@pytest.fixture()
def emp(client):
    """EMP001 — Blinkit employee, North region (sees the North LIVE demo stores)."""
    r = login(client, "EMP001")
    assert r.status_code == 200, r.text
    return auth(r.json()["access_token"])


@pytest.fixture()
def zepto_emp(client):
    r = login(client, "EMP002")
    assert r.status_code == 200, r.text
    return auth(r.json()["access_token"])


@pytest.fixture()
def make_user(db):
    """Create a throwaway user (any role / platform) directly in the database and delete it afterwards."""
    created: list[uuid.UUID] = []

    def _make(role: str = "employee", platform: str | None = None, region: str | None = None, password: str = DEMO_PASSWORD,
              must_change: bool = False, phone: str | None = None, active: bool = True, grants: tuple[str, ...] = ("orders.view", "orders.mark", "compliance.upload")):
        org = db.query(Organization).filter_by(slug="veekay").one()
        code = f"T{uuid.uuid4().hex[:7].upper()}"
        u = User(organization_id=org.id, employee_code=code, full_name=f"Test {role} {code}", phone=phone,
                 password_hash=hash_password(password), must_change_password=must_change, is_active=active,
                 status="active" if active else "deactivated")
        if platform:
            u.platform_organization_id = db.query(Organization).filter_by(slug=platform).one().id
        if region:
            from app.models.region import Region
            u.region_id = db.query(Region).filter_by(code=region).one().id
        db.add(u)
        db.flush()
        db.add(UserRole(user_id=u.id, role_id=db.query(Role).filter_by(code=role).one().id))
        if role == "employee":
            for g in grants:
                db.add(UserPermission(user_id=u.id, permission_id=db.query(Permission).filter_by(code=g).one().id))
        db.commit()
        created.append(u.id)
        return u.employee_code, password, u.id

    yield _make
    for uid in created:
        for model in (AttendanceSession, AttendanceRecord, LeaveRequest, RefreshSession, UserPermission, UserRole):
            db.query(model).filter(model.user_id == uid).delete()
        db.query(User).filter(User.id == uid).delete()
    db.commit()


@pytest.fixture()
def make_store(db):
    """Create throwaway stores (deleted afterwards, which also removes their entries and documents)."""
    created: list[uuid.UUID] = []

    def _make(code: str | None = None, platform: str = "blinkit", region: str | None = "NORTH", state: str = "Delhi",
              city: str = "New Delhi", vendor: str | None = "TEST VENDOR", status: str = "LIVE", entity: str | None = "BCPL", name: str | None = None):
        from app.models.region import Region
        org = db.query(Organization).filter_by(slug="veekay").one()
        s = Store(
            organization_id=org.id, partner_organization_id=db.query(Organization).filter_by(slug=platform).one().id,
            region_id=db.query(Region).filter_by(code=region).one().id if region else None,
            name=name or f"Test Store {uuid.uuid4().hex[:5]}", external_code=code or f"TST-{uuid.uuid4().hex[:6].upper()}",
            state=state, city=city, vendor_name=vendor, status=status, entity=entity,
        )
        db.add(s)
        db.commit()
        created.append(s.id)
        return s

    yield _make
    from app.models.order_entry import OrderEntry
    for sid in created:
        db.query(ComplianceDocument).filter(ComplianceDocument.store_id == sid).delete()
        db.query(OrderEntry).filter(OrderEntry.store_id == sid).delete()
        db.query(Store).filter(Store.id == sid).delete()
    db.commit()


def jpeg(color: str = "red", size: tuple[int, int] = (120, 80)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
