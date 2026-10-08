"""
A small in-process read cache for expensive, read-mostly endpoints (dashboard roll-ups, the admin store lists).

  * `get_or_set(key, ttl, factory)` returns a fresh-enough value, computing it at most ONCE even when many
    requests arrive together (single-flight): the others wait for that one result instead of each hitting the
    database. That is what keeps a burst of people opening the dashboard at 9 a.m. cheap.
  * Correct across workers and machines: every successful write bumps a counter in Postgres
    (`app_data_version`, see `invalidate`). A cached value is only served while that counter is unchanged, so a
    mark / correction / import made through one worker shows up on all of them within ~1 second. If the counter
    can't be read the cache falls back to its plain TTL.

Only organisation-wide aggregates go through here, keyed by organisation id — never one user's private data.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Hashable, TypeVar

from sqlalchemy import text

from app.db.session import engine

T = TypeVar("T")
log = logging.getLogger("veekay.cache")
_VERSION_MEMO_SECONDS = 1.0   # how long a worker trusts its last read of the shared counter
_MAX_ENTRIES = 300           # many different searches must never grow memory without bound


class TTLCache:
    def __init__(self) -> None:
        self._data: dict[Hashable, tuple[float, int, object]] = {}
        self._locks: dict[Hashable, threading.Lock] = {}
        self._guard = threading.Lock()
        self._generation = 0
        self._ver = (0.0, 0)  # (read at, value)

    # ---- the shared "data changed" counter -------------------------------------------------
    def _version(self) -> int:
        read_at, value = self._ver
        now = time.monotonic()
        if now - read_at < _VERSION_MEMO_SECONDS:
            return value
        try:
            with engine.connect() as conn:
                value = int(conn.execute(text("SELECT last_value FROM app_data_version")).scalar() or 0)
        except Exception:  # noqa: BLE001 — no counter (older DB / outage): behave as a plain TTL cache
            log.debug("data version unavailable", exc_info=True)
        self._ver = (now, value)
        return value

    def invalidate(self) -> None:
        """Call after a successful write: drop this worker's cache and tell every other worker the data changed."""
        self.clear()
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT nextval('app_data_version')"))
        except Exception:  # noqa: BLE001
            log.debug("could not bump data version", exc_info=True)
        self._ver = (0.0, self._ver[1])  # re-read on next use

    # ---- cache ------------------------------------------------------------------------------
    def _lock_for(self, key: Hashable) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _fresh(self, key: Hashable):
        hit = self._data.get(key)
        if hit and hit[0] > time.monotonic() and hit[1] == self._version():
            return hit
        return None

    def get_or_set(self, key: Hashable, ttl: float, factory: Callable[[], T]) -> T:
        hit = self._fresh(key)
        if hit:
            return hit[2]  # type: ignore[return-value]
        with self._lock_for(key):
            hit = self._fresh(key)  # someone else may have filled it while we waited
            if hit:
                return hit[2]  # type: ignore[return-value]
            generation, version = self._generation, self._version()
            value = factory()
            if generation == self._generation:  # a write landed while computing: don't store a stale result
                self._data[key] = (time.monotonic() + ttl, version, value)
                if len(self._data) > _MAX_ENTRIES:
                    self._evict()
            return value

    def _evict(self) -> None:
        """Drop expired entries, then the ones closest to expiring, until we're back under the cap."""
        now = time.monotonic()
        for k in [k for k, v in self._data.items() if v[0] <= now]:
            self._data.pop(k, None)
        while len(self._data) > _MAX_ENTRIES:
            self._data.pop(min(self._data, key=lambda k: self._data[k][0]), None)

    def clear(self) -> None:
        with self._guard:
            self._generation += 1
            self._data.clear()


read_cache = TTLCache()
