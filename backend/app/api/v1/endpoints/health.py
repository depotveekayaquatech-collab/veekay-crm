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

    try:
        storage.healthcheck()
        checks["storage"] = {"ok": True, "backend": settings.STORAGE_BACKEND}
    except Exception:  # noqa: BLE001
        checks["storage"] = {"ok": False, "backend": settings.STORAGE_BACKEND}

    healthy = all(c["ok"] for c in checks.values())
    body = {"status": "ready" if healthy else "degraded", "checks": checks, "environment": settings.ENVIRONMENT}
    if settings.RELEASE:
        body["release"] = settings.RELEASE
    return JSONResponse(body, status_code=200 if healthy else 503)
