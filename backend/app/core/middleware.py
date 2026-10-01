"""
HTTP middleware (pure ASGI, so streaming and large uploads are not buffered):

  RequestContextMiddleware — request id, timing, one structured log line per request
  RateLimitMiddleware      — per-IP limits; stricter for uploads / imports / PDF + Excel generation
  BodyLimitMiddleware      — refuses oversized request bodies up front (413)
  SecurityHeadersMiddleware— nosniff, no-framing, HSTS in production, no caching of API responses
  SelectiveGZip            — compresses JSON / text, never the PDFs, ZIPs and images
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.logging_config import request_id_var

log = logging.getLogger("app.request")
_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_API = settings.API_V1_PREFIX


def scope_ip(scope: Scope) -> str:
    """Caller IP; X-Forwarded-For only when we sit behind a trusted proxy (TRUST_PROXY_HEADERS)."""
    if settings.TRUST_PROXY_HEADERS:
        fwd = Headers(scope=scope).get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    client = scope.get("client")
    return (client[0] if client else "unknown")[:64]


# --------------------------------------------------------------------------
# request id + access log
# --------------------------------------------------------------------------

class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get("x-request-id", "")
        rid = incoming if _REQUEST_ID_OK.match(incoming) else uuid.uuid4().hex[:16]
        request_id_var.set(rid)  # left set on purpose: the 500 handler (outside this middleware) logs with it
        started = time.perf_counter()
        status_code = 500
        sent = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, sent
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode()))
                message["headers"] = headers
            elif message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path not in (f"{_API}/health", f"{_API}/ready"):   # probes would drown the log
                log.log(
                    logging.WARNING if status_code >= 500 else logging.INFO,
                    "%s %s -> %s", scope.get("method"), path, status_code,
                    extra={"method": scope.get("method"), "path": path, "status": status_code,
                           "ms": round((time.perf_counter() - started) * 1000, 1), "ip": scope_ip(scope), "bytes": sent},
                )


# --------------------------------------------------------------------------
# rate limiting
# --------------------------------------------------------------------------

_HEAVY = [
    ("POST", re.compile(rf"^{_API}/(compliance/(upload|bulk|summary-pdf|download)|orders/import|stores/import|employees/import|cards/zip)$")),
    ("GET", re.compile(rf"^{_API}/(cards/pdf|orders/matrix/export)$")),
]
_AUTH = re.compile(rf"^{_API}/auth/(login|refresh)$")
_AUTH_PER_MIN = 120


class _Window:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def take(self, key: str, limit: int, window: float = 60.0) -> int:
        """0 = allowed (and counted); otherwise seconds to wait."""
        now = time.monotonic()
        with self.lock:
            dq = self.hits[key]
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= limit:
                return max(1, int(window - (now - dq[0])) + 1)
            dq.append(now)
            if len(self.hits) > 20_000:  # bound memory under a spray of distinct IPs
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > window]:
                    del self.hits[k]
            return 0

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


rate_windows = _Window()


def _bucket(method: str, path: str) -> tuple[str, int] | None:
    if not path.startswith(_API) or method == "OPTIONS" or path in (f"{_API}/health", f"{_API}/ready"):
        return None
    for m, rx in _HEAVY:
        if method == m and rx.match(path):
            return "heavy", settings.RATE_LIMIT_HEAVY_PER_MIN
    if path.startswith(f"{_API}/public/"):
        return "public", settings.RATE_LIMIT_PUBLIC_PER_MIN
    if _AUTH.match(path):
        return "auth", _AUTH_PER_MIN
    return "default", settings.RATE_LIMIT_DEFAULT_PER_MIN


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.RATE_LIMIT_ENABLED:
            await self.app(scope, receive, send)
            return
        rule = _bucket(scope.get("method", "GET"), scope.get("path", ""))
        if rule is not None:
            name, limit = rule
            wait = rate_windows.take(f"{name}:{scope_ip(scope)}", limit)
            if wait:
                resp = JSONResponse(
                    {"detail": f"Too many requests. Please slow down and try again in {wait} second{'s' if wait != 1 else ''}."},
                    status_code=429, headers={"Retry-After": str(wait)},
                )
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------
# request body size
# --------------------------------------------------------------------------

class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            declared = Headers(scope=scope).get("content-length")
            if declared and declared.isdigit() and int(declared) > settings.MAX_REQUEST_BYTES:
                lim = settings.MAX_REQUEST_BYTES
                human = f"{lim // (1024 * 1024)} MB" if lim >= 1024 * 1024 else f"{max(1, lim // 1024)} KB"
                resp = JSONResponse({"detail": f"That upload is too large (the limit is {human} per request)."}, status_code=413)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


# --------------------------------------------------------------------------
# security headers
# --------------------------------------------------------------------------

_DOC_PATHS = (f"{_API}/docs", "/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.SECURITY_HEADERS_ENABLED:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        is_doc = path.startswith(_DOC_PATHS)

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = Headers(raw=message.get("headers", []))
                extra: list[tuple[bytes, bytes]] = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
                ]
                if not is_doc:  # Swagger UI needs scripts; the API itself never serves a page
                    extra.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                if settings.ENVIRONMENT.strip().lower() == "production":
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                if path.startswith(_API) and "cache-control" not in h:
                    extra.append((b"cache-control", b"no-store"))  # API responses carry personal data
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, wrapped)


# --------------------------------------------------------------------------
# gzip for text, not for already-compressed downloads
# --------------------------------------------------------------------------

_NO_GZIP = re.compile(r"/(cards/(pdf|zip)|compliance/(download|summary-pdf|[0-9a-f-]{36}/file)|orders/matrix/export)$")


class SelectiveGZip:
    def __init__(self, app: ASGIApp, minimum_size: int = 1024) -> None:
        self.plain = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not _NO_GZIP.search(scope.get("path", "")):
            await self.gzip(scope, receive, send)
        else:
            await self.plain(scope, receive, send)
