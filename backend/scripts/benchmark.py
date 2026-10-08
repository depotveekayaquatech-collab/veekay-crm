"""
Read-only API benchmark: time, SQL query count and payload size for the endpoints people use most.

    cd backend
    python scripts/benchmark.py            # against the database in .env

It never writes: it signs in as ADMIN001 by overriding the auth dependency in-process, so no password and no
session rows are needed. "cold" clears the shared read cache first (the full cost of computing the answer);
"warm" is a repeat request served from the cache. Run it before and after a change on the same machine, and
compare the unchanged endpoints (calendar, partners, activity) to judge how noisy the machine was.
"""
import os
import statistics
import sys
import time
import zlib
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "ERROR")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.cache import read_cache  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

db = SessionLocal()
admin = db.query(User).filter(User.employee_code == "ADMIN001").one()
db.close()
app.dependency_overrides[deps.get_current_user] = lambda: admin

queries = {"n": 0}


@event.listens_for(engine, "before_cursor_execute")
def _count(conn, cur, stmt, params, ctx, many):  # noqa: ANN001
    queries["n"] += 1


client = TestClient(app)
today = date.today()
d60, d30, d365 = ((today - timedelta(days=n)).isoformat() for n in (59, 29, 364))
with engine.connect() as c:
    store_id = c.execute(text("select id from stores where status='LIVE' limit 1")).scalar()

CASES = [
    ("my-stores (admin: all live stores)", "/orders/my-stores"),
    ("dashboard insights", "/orders/insights"),
    ("daily overview (blinkit)", "/orders/daily-overview?partner=blinkit&day_offset=0"),
    ("daily overview (zepto)", "/orders/daily-overview?partner=zepto&day_offset=0"),
    ("pending (zepto)", "/orders/pending?partner=zepto&day_offset=0"),
    ("report 60d by partner", f"/orders/report?start={d60}&end={today}&group_by=partner"),
    ("report 30d by store, top 6", f"/orders/report?start={d30}&end={today}&group_by=store&limit=6"),
    ("report 365d by store", f"/orders/report?start={d365}&end={today}&group_by=store"),
    ("matrix (30 days)", f"/orders/matrix?start={d30}&end={today}"),
    ("inventory", "/orders/inventory"),
    ("all stores (one request)", "/stores/all"),
    ("stores page 1", "/stores?page=1&page_size=100"),
    ("compliance repository", f"/compliance/stores?month={today:%Y-%m}&page_size=50"),
    ("card vendors", "/cards/vendors"),
    ("employees", "/employees?page=1"),
    ("activity log", "/activity?page=1"),
    ("test reports", "/test-reports?partner=zepto"),
    ("-- unchanged yardstick: calendar", f"/orders/calendar?store_id={store_id}"),
    ("-- unchanged yardstick: partners", "/partners"),
]


def get(path):
    queries["n"] = 0
    t = time.perf_counter()
    r = client.get("/api/v1" + path, headers={"Accept-Encoding": "identity"})
    return r, (time.perf_counter() - t) * 1000, queries["n"]


def cold(path):
    read_cache.clear()
    read_cache._ver = (0.0, 0)
    return get(path)


for _ in range(3):  # warm the process so the first endpoint doesn't pay for imports and connections
    get("/partners")

print(f"{'endpoint':38} {'cold ms':>8} {'warm ms':>8} {'sql#':>5} {'raw KB':>8} {'gzip KB':>8}")
for name, path in CASES:
    colds, warms, n, r = [], [], 0, None
    for _ in range(3):
        r, ms, n = cold(path)
        colds.append(ms)
        warms.append(get(path)[1])
    if r.status_code != 200:
        print(f"{name:38} HTTP {r.status_code}")
        continue
    raw = len(r.content)
    print(f"{name:38} {statistics.median(colds):8.0f} {statistics.median(warms):8.0f} {n:5d} {raw / 1024:8.1f} {len(zlib.compress(r.content, 6)) / 1024:8.1f}")
