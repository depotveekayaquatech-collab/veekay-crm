"""Liveness / readiness probes. No secrets, no per-user data."""
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])

# The storage probe is a billed request to the bucket (HeadBucket, Class B). An uptime monitor may call /ready every minute,
# so the answer is reused for this long: the bucket is asked at most 6 times an hour (about 4,300 requests a month) however often
# /ready is polled. The database part of /ready is always live, and an upload that cannot reach the bucket fails immediately
# with its own clear error, so a storage outage is never hidden from the people using it.
_STORAGE_PROBE_SECONDS = 600.0
_storage_probe: tuple[float, bool] | None = None


def reset_storage_probe() -> None:
    """Forget the last storage answer (tests, and anything that changes the storage settings)."""
    global _storage_probe
    _storage_probe = None


def _storage_ok() -> bool:
    global _storage_probe
    now = time.monotonic()
    if _storage_probe is not None and now - _storage_probe[0] < _STORAGE_PROBE_SECONDS:
        return _storage_probe[1]
    try:
        storage.healthcheck()
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    _storage_probe = (now, ok)
    return ok


@router.get("/health")
def health() -> dict:
    """Liveness: the process is up. Cheap and dependency-free — what the hosting platform pings."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: can this instance do real work? Checks the database, file storage and migration state."""
    checks: dict[str, dict] = {}

    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "ms": round((time.perf_counter() - started) * 1000, 1)}
        try:
            rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            checks["migrations"] = {"ok": rev is not None, "revision": rev}
        except Exception:  # noqa: BLE001
            db.rollback()
            checks["migrations"] = {"ok": False, "revision": None}
    except Exception:  # noqa: BLE001
        checks["database"] = {"ok": False}

    checks["storage"] = {"ok": _storage_ok(), "backend": settings.STORAGE_BACKEND}

    healthy = all(c["ok"] for c in checks.values())
    body = {"status": "ready" if healthy else "degraded", "checks": checks, "environment": settings.ENVIRONMENT}
    if settings.RELEASE:
        body["release"] = settings.RELEASE
    return JSONResponse(body, status_code=200 if healthy else 503)
