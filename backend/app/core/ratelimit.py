"""
Failed-login throttle per client IP.

Per-account lockout stops guessing one account; this stops one network
guessing many accounts (and limits lockout-griefing). Only FAILED attempts
count, so an office full of people signing in at 9am is never throttled.

In-memory and per process: fine for a single API instance. With several
instances, back it with Redis/the database instead.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings


class FailureLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, dq: deque[float], now: float, window: float) -> None:
        while dq and now - dq[0] > window:
            dq.popleft()

    def blocked_for(self, key: str) -> int:
        """Seconds until this key may try again (0 = allowed)."""
        window = settings.LOGIN_IP_WINDOW_MINUTES * 60
        now = time.monotonic()
        with self._lock:
            dq = self._hits.get(key)
            if not dq:
                return 0
            self._trim(dq, now, window)
            if len(dq) >= settings.LOGIN_IP_MAX_FAILURES:
                return max(1, int(window - (now - dq[0])))
            if not dq:
                self._hits.pop(key, None)
            return 0

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._hits[key].append(now)
            if len(self._hits) > 10_000:  # bound memory under a spray attack
                window = settings.LOGIN_IP_WINDOW_MINUTES * 60
                for k in list(self._hits):
                    self._trim(self._hits[k], now, window)
                    if not self._hits[k]:
                        del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_failures = FailureLimiter()


def client_ip(request: Request) -> str:
    """The caller's IP. X-Forwarded-For is honoured only behind a trusted proxy (TRUST_PROXY_HEADERS)."""
    if settings.TRUST_PROXY_HEADERS:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]
