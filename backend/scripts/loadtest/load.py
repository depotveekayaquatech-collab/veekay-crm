"""
Concurrent-user load test against the API on :8010 (veekay_load: 1,500 stores, 135k orders ...).

    python load.py [phase ...]       phases: login emp10 emp25 emp50 mixed search orders upload   (default: all)

Every virtual user is a real login with its own token. Latencies are measured per endpoint; the server's
(workers + postgres) CPU and memory are sampled every second. 409 on `mark` (store already marked today by
a colleague in the same region) is a normal business answer, not an error.
"""
import asyncio
import io
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

import httpx  # noqa: E402
import psutil  # noqa: E402

BASE = "http://127.0.0.1:8010/api/v1"
PW = "Load-Test-Pass-1"
TODAY = date.today()
random.seed(11)


class Stats:
    def __init__(self):
        self.lat = defaultdict(list)
        self.status = defaultdict(lambda: defaultdict(int))
        self.size = defaultdict(list)
        self.errors = defaultdict(int)
        self.t0 = time.time()
        self.t1 = None

    def add(self, name, ms, status, nbytes, ok):
        self.lat[name].append(ms)
        self.status[name][status] += 1
        self.size[name].append(nbytes)
        if not ok:
            self.errors[name] += 1

    def report(self, title, extra=""):
        dur = (self.t1 or time.time()) - self.t0
        total = sum(len(v) for v in self.lat.values())
        errs = sum(self.errors.values())
        print(f"\n=== {title}  ({dur:.0f}s, {total} requests, {total / dur:.1f} req/s, {errs} errors) {extra}")
        print(f"{'endpoint':34}{'n':>6}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}{'KB':>8}{'err':>5}  statuses")
        for name in sorted(self.lat):
            v = sorted(self.lat[name])
            q = lambda p: v[min(len(v) - 1, int(len(v) * p))]
            sts = ",".join(f"{k}:{n}" for k, n in sorted(self.status[name].items(), key=lambda kv: str(kv[0])))
            print(f"{name:34}{len(v):>6}{q(.5):>8.0f}{q(.95):>8.0f}{q(.99):>8.0f}{v[-1]:>8.0f}{statistics.mean(self.size[name]) / 1024:>8.1f}{self.errors[name]:>5}  {sts}")
        return total / dur, errs


class Sampler:
    """CPU / memory of the API workers and postgres, once a second."""
    def __init__(self):
        self.api_cpu, self.api_rss, self.pg_cpu, self.pg_rss = [], [], [], []
        self.stop = False

    def find(self):
        api, pg = [], []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
                if "run_server.py" in cmd or ("multiprocessing" in cmd and "spawn_main" in cmd and "python" in (p.info["name"] or "").lower() and "load.py" not in cmd):
                    api.append(p)
                elif (p.info["name"] or "").lower().startswith("postgres"):
                    pg.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return api, pg

    async def run(self):
        api, pg = self.find()
        for p in api + pg:
            p.cpu_percent(None)
        while not self.stop:
            await asyncio.sleep(1)
            try:
                self.api_cpu.append(sum(p.cpu_percent(None) for p in api)); self.api_rss.append(sum(p.memory_info().rss for p in api) / 2**20)
                self.pg_cpu.append(sum(p.cpu_percent(None) for p in pg)); self.pg_rss.append(sum(p.memory_info().rss for p in pg) / 2**20)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def summary(self):
        f = lambda xs: (f"avg {statistics.mean(xs):.0f}% peak {max(xs):.0f}%" if xs else "n/a")
        m = lambda xs: (f"peak {max(xs):.0f} MB" if xs else "n/a")
        return (f"API workers CPU {f(self.api_cpu)} (of 800% = 8 threads), RAM {m(self.api_rss)} | "
                f"Postgres CPU {f(self.pg_cpu)}, RAM {m(self.pg_rss)}")


async def call(c, st, name, method, url, ok=(200,), **kw):
    t = time.perf_counter()
    try:
        r = await c.request(method, BASE + url, **kw)
        ms = (time.perf_counter() - t) * 1000
        st.add(name, ms, r.status_code, len(r.content), r.status_code in ok)
        return r
    except Exception as e:  # noqa: BLE001 — timeouts / connection errors count as errors
        st.add(name, (time.perf_counter() - t) * 1000, type(e).__name__, 0, False)
        return None


async def login(c, st, code, password=PW, name="login"):
    r = await call(c, st, name, "POST", "/auth/login", json={"employee_code": code, "password": password, "organization_slug": "veekay"})
    if r is None or r.status_code != 200:
        return None
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def employees(n):
    nz = min(10, n // 6)
    return [f"EMPB{i + 1:03d}" for i in range(n - nz)] + [f"EMPZ{i + 1:03d}" for i in range(nz)]


async def employee_session(c, st, code, seconds, think=(1.0, 3.0)):
    h = await login(c, st, code)
    if not h:
        return
    await call(c, st, "GET /auth/me", "GET", "/auth/me", headers=h)
    r = await call(c, st, "GET /orders/my-stores", "GET", "/orders/my-stores", headers=h)
    stores = [s.get("id") or s.get("store_id") for s in (r.json() if r is not None and r.status_code == 200 else [])]
    end = time.time() + seconds
    while time.time() < end and stores:
        await asyncio.sleep(random.uniform(*think))
        roll = random.random()
        sid = random.choice(stores)
        if roll < .35:
            await call(c, st, "GET /orders/calendar", "GET", f"/orders/calendar?store_id={sid}", headers=h)
        elif roll < .65:
            await call(c, st, "POST /orders/mark", "POST", "/orders/mark", ok=(200, 409), headers=h,
                       json={"store_id": sid, "order_date": TODAY.isoformat(), "bottle_count": random.randint(5, 60)})
        elif roll < .75:
            await call(c, st, "GET /orders/my-stores", "GET", "/orders/my-stores", headers=h)
        elif roll < .85:
            await call(c, st, "GET /tickets", "GET", "/tickets?page=1&page_size=20", headers=h)
        elif roll < .92:
            await call(c, st, "GET /compliance/stores", "GET", "/compliance/stores?page=1&page_size=50", headers=h)
        else:
            await call(c, st, "GET /cash-purchases", "GET", "/cash-purchases?page_size=20", headers=h)


async def admin_session(c, st, h, seconds, think=(2.0, 5.0)):
    s, e = (TODAY - timedelta(days=30)).isoformat(), TODAY.isoformat()
    calls = [("GET /orders/insights", "/orders/insights"), ("GET /orders/daily-overview", "/orders/daily-overview?partner=blinkit"),
             ("GET /orders/pending", "/orders/pending?partner=zepto"), ("GET /orders/report", f"/orders/report?start={s}&end={e}&group_by=region"),
             ("GET /orders/matrix", f"/orders/matrix?start={s}&end={e}&page_size=25"), ("GET /stores (page)", "/stores?page=1&page_size=25")]
    end = time.time() + seconds
    while time.time() < end:
        for name, url in calls:
            if time.time() >= end:
                break
            await call(c, st, name, "GET", url, headers=h)
            await asyncio.sleep(random.uniform(*think))


async def hammer(c, st, h, seconds, calls):
    """No think time: every user fires the next request as soon as the last one returns (a stress test)."""
    end = time.time() + seconds
    while time.time() < end:
        name, url = random.choice(calls)
        await call(c, st, name, "GET", url, headers=h)


def client():
    return httpx.AsyncClient(timeout=httpx.Timeout(60.0), limits=httpx.Limits(max_connections=400, max_keepalive_connections=200))


async def with_sampler(coro_factory, title):
    sm = Sampler()
    task = asyncio.create_task(sm.run())
    st = Stats()
    await coro_factory(st)
    st.t1 = time.time()
    sm.stop = True
    await task
    rps, errs = st.report(title, "")
    print("    resources:", sm.summary())
    return rps, errs, st, sm


async def phase_login():
    async with client() as c:
        for n in (10, 25, 50):
            async def go(st, n=n):
                await asyncio.gather(*(login(c, st, code) for code in employees(n)))
            await with_sampler(go, f"LOGIN burst: {n} users sign in at the same instant (bcrypt cost 12)")


async def phase_emp(n, seconds=40):
    async with client() as c:
        async def go(st):
            await asyncio.gather(*(employee_session(c, st, code, seconds) for code in employees(n)))
        await with_sampler(go, f"REALISTIC EMPLOYEE WORKLOAD: {n} concurrent employees, {seconds}s, 1-3 s think time")


async def phase_mixed(seconds=60):
    async with client() as c:
        st0 = Stats()
        admin_h = await login(c, st0, "ADMIN001", "Pass@123")
        async def go(st):
            tasks = [employee_session(c, st, code, seconds) for code in employees(50)]
            tasks += [admin_session(c, st, admin_h, seconds) for _ in range(10)]
            await asyncio.gather(*tasks)
        await with_sampler(go, f"MIXED PEAK: 50 employees + 10 admins on dashboards, {seconds}s")


async def phase_search(seconds=30):
    async with client() as c:
        st0 = Stats()
        h = await login(c, st0, "ADMIN001", "Pass@123")
        terms = ["bhiwandi", "pune", "BLK-LD-01", "ZEP-LD-12", "thane", "sector", "dark store", "gurugram"]
        search = [("GET /stores?search= (25 rows)", f"/stores?search={t}&page=1&page_size=25") for t in terms]
        async def go(st):
            await asyncio.gather(*(hammer(c, st, h, seconds, search) for _ in range(25)))
        await with_sampler(go, f"SEARCH under load: 25 users, no pauses, server-side search, {seconds}s")
        async def go_all(st):
            await asyncio.gather(*(hammer(c, st, h, seconds, [("GET /stores/all (1,500 rows)", "/stores/all")]) for _ in range(25)))
        await with_sampler(go_all, f"SAME 25 users loading /stores/all instead (what the browser does today), {seconds}s")


async def phase_orders(seconds=30):
    async with client() as c:
        st0 = Stats()
        h = await login(c, st0, "ADMIN001", "Pass@123")
        s, e = (TODAY - timedelta(days=30)).isoformat(), TODAY.isoformat()
        calls = [("GET /orders/matrix (31d x 25 stores)", f"/orders/matrix?start={s}&end={e}&page_size=25"),
                 ("GET /orders/matrix p.20", f"/orders/matrix?start={s}&end={e}&page=20&page_size=25"),
                 ("GET /orders/report (31d)", f"/orders/report?start={s}&end={e}&group_by=region"),
                 ("GET /orders/pending", "/orders/pending?partner=blinkit")]
        async def go(st):
            await asyncio.gather(*(hammer(c, st, h, seconds, calls) for _ in range(25)))
        await with_sampler(go, f"ORDER LISTS under load: 25 users, no pauses, {seconds}s")


def make_jpeg(mb):
    """A phone-photo-sized JPEG: noise compresses badly, so tune the size until it is about `mb` MB."""
    from PIL import Image
    w, h = 1800, 1350
    while True:
        img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        if len(buf.getvalue()) < mb * 1024 * 1024 or w <= 600:
            return buf.getvalue()
        w, h = int(w * .85), int(h * .85)


async def upload_one(c, st, code, blob, photos, idx=0, same=False):
    h = await login(c, st, code, name="login (setup)")
    if not h:
        return
    r = await call(c, st, "GET /orders/my-stores", "GET", "/orders/my-stores", headers=h)
    lst = r.json() if r is not None and r.status_code == 200 else []
    store = (lst[0 if same else idx % len(lst)].get("id") if lst else None)
    t = time.perf_counter()
    await call(c, st, f"POST /cash-purchases (proof {len(blob) / 2**20:.1f} MB)", "POST", "/cash-purchases", ok=(201,), headers=h,
               data={"kind": "OFFICE", "purchase_date": TODAY.isoformat(), "category": "MILK", "amount": "120"},
               files={"proof": ("proof.jpg", blob, "image/jpeg")})
    if store:
        await call(c, st, f"POST /compliance/upload ({photos} photos -> merged PDF)", "POST", "/compliance/upload", ok=(200,), headers=h,
                   data={"store_id": store, "month": TODAY.strftime("%Y-%m"), "kind": "payment"},
                   files=[("files", (f"p{i}.jpg", blob, "image/jpeg")) for i in range(photos)])


async def phase_upload():
    blob = make_jpeg(1.8)
    print(f"{chr(10)}(upload test image: {len(blob) / 2**20:.2f} MB JPEG)")
    async with client() as c:
        for n in (5, 10, 25):
            async def go(st, n=n):
                await asyncio.gather(*(upload_one(c, st, code, blob, 3, i) for i, code in enumerate(employees(n))))
            await with_sampler(go, f"SIMULTANEOUS UPLOADS: {n} employees, each a proof + a 3-photo document, different stores")
        async def same(st):
            await asyncio.gather(*(upload_one(c, st, code, blob, 3, 0, same=True) for code in employees(10)))
        await with_sampler(same, "CONTENTION CASE: 10 employees upload the SAME store / month / document type at once")


PHASES = {"login": phase_login, "emp10": lambda: phase_emp(10), "emp25": lambda: phase_emp(25), "emp50": lambda: phase_emp(50),
          "mixed": phase_mixed, "search": phase_search, "orders": phase_orders, "upload": phase_upload}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PHASES)
    for name in wanted:
        asyncio.run(PHASES[name]())
        sys.stdout.flush()
