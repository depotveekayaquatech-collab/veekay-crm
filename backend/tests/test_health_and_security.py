"""Health probes and the HTTP hardening layer: headers, request ids, error handling, rate limits, body limit."""
import pytest
from fastapi import APIRouter

from app.core import middleware as mw
from app.core.config import settings
from app.main import app

from .conftest import API, auth, login


# ---------------------------------------------------------------- health
def test_liveness_is_cheap_and_open(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readiness_reports_database_migrations_and_storage(client):
    r = client.get(f"{API}/ready")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ready"
    assert body["checks"]["database"]["ok"] and body["checks"]["storage"]["ok"]
    assert body["checks"]["migrations"]["revision"]            # the Alembic revision the database is at


def test_readiness_turns_503_when_a_dependency_is_down(client, monkeypatch):
    from app.core import storage

    def boom():
        raise RuntimeError("bucket unreachable")

    monkeypatch.setattr(storage, "healthcheck", boom)
    r = client.get(f"{API}/ready")
    assert r.status_code == 503 and r.json()["status"] == "degraded" and r.json()["checks"]["storage"]["ok"] is False
    assert "bucket unreachable" not in r.text                  # no internals leak to the caller


# ---------------------------------------------------------------- headers / request id
def test_security_headers_on_api_responses(client):
    h = client.get(f"{API}/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["cache-control"] == "no-store"
    assert "geolocation=()" in h["permissions-policy"]


def test_hsts_only_in_production(client, monkeypatch):
    assert "strict-transport-security" not in client.get(f"{API}/health").headers
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert "max-age=31536000" in client.get(f"{API}/health").headers["strict-transport-security"]


def test_request_id_is_generated_and_a_sane_incoming_one_is_kept(client):
    assert len(client.get(f"{API}/health").headers["x-request-id"]) >= 8
    assert client.get(f"{API}/health", headers={"X-Request-ID": "trace-abc-12345"}).headers["x-request-id"] == "trace-abc-12345"
    assert client.get(f"{API}/health", headers={"X-Request-ID": "bad id!!"}).headers["x-request-id"] != "bad id!!"


def test_unhandled_errors_return_a_safe_body_with_a_reference(client):
    router = APIRouter()

    @router.get("/__boom")
    def boom():
        raise ZeroDivisionError("secret internal detail")

    app.include_router(router, prefix=API)
    try:
        r = TestClientNoRaise().get(f"{API}/__boom")
    finally:
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != f"{API}/__boom"]
    assert r.status_code == 500
    body = r.json()
    assert "secret internal detail" not in r.text and "ZeroDivisionError" not in r.text
    assert body["request_id"] and "detail" in body


def TestClientNoRaise():
    """Starlette's TestClient re-raises server errors by default; production does not."""
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


def test_api_docs_are_off_when_docs_disabled():
    # the app decides at start-up; check the rule itself so a regression in it is caught
    import importlib
    src = open(importlib.import_module("app.main").__file__, encoding="utf-8").read()
    assert 'settings.ENVIRONMENT.strip().lower() != "production"' in src and "docs_url=" in src


# ---------------------------------------------------------------- rate limiting
@pytest.fixture()
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_DEFAULT_PER_MIN", 5)
    monkeypatch.setattr(settings, "RATE_LIMIT_HEAVY_PER_MIN", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_PUBLIC_PER_MIN", 3)
    mw.rate_windows.reset()


def test_default_limit_blocks_with_429_and_retry_after(client, admin, limits_on):
    codes = [client.get(f"{API}/auth/me", headers=admin).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    r = client.get(f"{API}/auth/me", headers=admin)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and "Too many requests" in r.json()["detail"]


def test_a_429_still_carries_cors_headers_so_the_browser_can_read_it(client, admin, limits_on):
    for _ in range(6):
        r = client.get(f"{API}/auth/me", headers={**admin, "Origin": "http://localhost:5173"})
    assert r.status_code == 429 and r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_health_and_readiness_are_never_limited(client, limits_on):
    assert {client.get(f"{API}/health").status_code for _ in range(20)} == {200}
    assert {client.get(f"{API}/ready").status_code for _ in range(20)} == {200}


def test_heavy_endpoints_have_a_stricter_limit(client, admin, limits_on):
    codes = [client.get(f"{API}/orders/matrix/export?start=2026-09-01&end=2026-09-02", headers=admin).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]


def test_public_endpoint_is_limited_separately(client, limits_on):
    codes = [client.get(f"{API}/public/count?s=00000000-0000-0000-0000-000000000000&sig=x").status_code for _ in range(5)]
    assert codes[:3] == [404, 404, 404] and codes[3:] == [429, 429]


def test_limits_are_per_client_ip(client, limits_on, monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    for _ in range(6):
        client.get(f"{API}/auth/me", headers={"X-Forwarded-For": "10.0.0.1"})
    assert client.get(f"{API}/auth/me", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 429
    assert client.get(f"{API}/auth/me", headers={"X-Forwarded-For": "10.0.0.2"}).status_code == 401   # someone else is unaffected


def test_forwarded_header_is_ignored_when_not_behind_a_proxy(client, limits_on):
    for i in range(6):
        client.get(f"{API}/auth/me", headers={"X-Forwarded-For": f"10.9.9.{i}"})      # spoofing a new IP each time
    assert client.get(f"{API}/auth/me", headers={"X-Forwarded-For": "10.9.9.99"}).status_code == 429


# ---------------------------------------------------------------- request size
def test_oversized_request_bodies_are_refused_up_front(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BYTES", 2000)
    r = client.post(f"{API}/auth/login", json={"employee_code": "x", "password": "y" * 5000})
    assert r.status_code == 413 and "too large" in r.json()["detail"]
    assert client.post(f"{API}/auth/login", json={"employee_code": "x", "password": "y"}).status_code == 401


# ---------------------------------------------------------------- gzip
def test_json_is_compressed_but_downloads_are_not(client, admin):
    big = client.get(f"{API}/orders/inventory", headers={**admin, "Accept-Encoding": "gzip"})
    assert big.status_code == 200 and big.headers.get("content-encoding") == "gzip"
    pdf = client.get(f"{API}/cards/pdf?partner=blinkit&vendor=Local%20Vendor", headers={**admin, "Accept-Encoding": "gzip"})
    assert "content-encoding" not in pdf.headers


def test_authenticated_routes_reject_missing_tokens(client):
    for path in ("/auth/me", "/orders/insights", "/compliance/stores", "/attendance/day", "/cards/vendors", "/employees"):
        assert client.get(f"{API}{path}").status_code == 401, path
