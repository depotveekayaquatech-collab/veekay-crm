"""POST /busy-sync: how the Busy 21 PC (later) sends bills and payments in. Secured by a shared secret in the x-api-key header (BUSY_SYNC_API_KEY)."""
import hmac
import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ratelimit import FailureLimiter, client_ip
from app.db.session import get_db
from app.models.busy_ledger import SOURCE_API, STATUS_FAILED
from app.services.busy_sync_service import MODE_REPLACE, record_failure, run_sync

router = APIRouter(prefix="/busy-sync", tags=["busy-sync"])
log = logging.getLogger("busy_sync")

# Wrong-key attempts per client IP (same limits as failed logins): a guesser is locked out for a while, a correct key is never slowed down.
_key_failures = FailureLimiter()


class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")


class SyncRequest(BaseModel):
    mode: Literal["upsert", "replace_period"] = "upsert"
    period: Period | None = None
    vendor_codes: list[str] = Field(default_factory=list, max_length=5000)      # replace_period only: vendors to clear even if they have no rows left
    entries: list[Any]

    @model_validator(mode="after")
    def _period_rules(self) -> "SyncRequest":
        if self.mode == MODE_REPLACE:
            if self.period is None:
                raise ValueError("period {from, to} is required for mode replace_period")
            if self.period.from_date > self.period.to_date:
                raise ValueError("period.from must not be after period.to")
        return self


def caller_ip(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    """The dependency that authenticates the call (and returns the caller's IP). Runs before the body is checked, so a wrong key is always a 401."""
    configured = settings.BUSY_SYNC_API_KEY
    if not configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Busy sync is not switched on (BUSY_SYNC_API_KEY is not set).")
    ip = client_ip(request)
    wait = _key_failures.blocked_for(ip)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many wrong keys. Try again in {wait} seconds.", headers={"Retry-After": str(wait)})
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), configured.encode()):
        _key_failures.record_failure(ip)
        log.warning("busy sync rejected: wrong or missing x-api-key from %s", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key.", headers={"WWW-Authenticate": "ApiKey"})
    return ip


@router.post("")
def busy_sync(body: dict[str, Any], ip: str = Depends(caller_ip), db: Session = Depends(get_db)) -> JSONResponse:
    """Send Busy entries. `mode` "upsert" (default) adds new entries and updates edited ones; "replace_period" (with `period`) also removes
    API-sent entries in that period that Busy no longer has, for the vendors in the request (plus any in `vendor_codes`).
    Answers 200 with the counts and a per-row error list (valid rows are processed even when some are rejected), or 422 when every row was rejected.
    Send an empty `entries` list as a heartbeat when nothing changed, so the "last updated" time stays fresh."""
    started = datetime.now(timezone.utc)
    try:
        req = SyncRequest.model_validate(body)
    except ValidationError as exc:
        problems = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors(include_url=False, include_context=False, include_input=False)]
        record_failure(db, started=started, source=SOURCE_API, mode=str(body.get("mode") or "") or None, period=None, triggered_by=ip, received=0,
                       message=f"Request body rejected: {problems[0]['field']}: {problems[0]['message']}")
        return JSONResponse(status_code=422, content={"status": STATUS_FAILED, "detail": problems})
    if len(req.entries) > settings.BUSY_SYNC_MAX_ROWS:
        record_failure(db, started=started, source=SOURCE_API, mode=req.mode, period=None, triggered_by=ip, received=len(req.entries),
                       message=f"Too many entries in one request (limit {settings.BUSY_SYNC_MAX_ROWS}).")
        return JSONResponse(status_code=413, content={"status": STATUS_FAILED, "detail": f"Send at most {settings.BUSY_SYNC_MAX_ROWS} entries per request; split the batch."})
    period = (req.period.from_date, req.period.to_date) if req.period and req.mode == MODE_REPLACE else None
    outcome = run_sync(db, entries=req.entries, mode=req.mode, period=period, vendor_codes=req.vendor_codes, source=SOURCE_API, triggered_by=ip)
    return JSONResponse(status_code=422 if outcome.status == STATUS_FAILED else 200, content=outcome.to_dict())
