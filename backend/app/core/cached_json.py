"""
Serve a big, organisation-wide JSON list from the shared read cache, already serialised AND already gzipped.

Without this, every request for a 550 KB list re-validated and re-serialised it, then compressed it again.
Here the work happens once per change (see core/cache.py for when it is dropped) and a request is just a
byte copy. Clients that don't accept gzip get the plain bytes; the gzip middleware leaves a response that
already carries `Content-Encoding` alone.
"""
from __future__ import annotations

import gzip
from typing import Callable, Hashable

from fastapi import Request, Response

from app.core.cache import read_cache
from app.core.config import settings


def _pack(raw: bytes) -> tuple[bytes, bytes | None]:
    return raw, (gzip.compress(raw, 5, mtime=0) if len(raw) >= 1024 else None)


def cached_json_response(request: Request, key: Hashable, build: Callable[[], bytes]) -> Response:
    ttl = settings.DASHBOARD_CACHE_SECONDS
    raw, gz = read_cache.get_or_set(key, ttl, lambda: _pack(build())) if ttl else _pack(build())
    headers = {"Vary": "Accept-Encoding"}
    if gz is not None and "gzip" in request.headers.get("accept-encoding", "").lower():
        return Response(content=gz, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(content=raw, media_type="application/json", headers=headers)
