import html
import logging
import uuid
from contextlib import asynccontextmanager

from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core import scheduler
from app.core.config import settings
from app.core.storage import StorageUnavailable
from app.db.session import get_db
from app.services import card_service
from app.services.cash_purchase_service import DuplicatePurchase
from app.core.logging_config import request_id_var, setup_logging
from app.core.middleware import (
    BodyLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    CacheInvalidationMiddleware,
    SelectiveGZip,
)

setup_logging()
log = logging.getLogger("app")


def _init_sentry() -> None:
    """Forward unhandled errors to Sentry when SENTRY_DSN is set. No request bodies, no personal data."""
    if not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk
    except ImportError:  # the package is in requirements.txt; never let monitoring stop the app starting
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed; error tracking is off.")
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.RELEASE or None,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
    )
    log.info("Sentry error tracking enabled.")


_init_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


# The interactive API docs list every endpoint — handy in development, an information leak in production.
_docs_on = settings.DOCS_ENABLED if settings.DOCS_ENABLED is not None else settings.ENVIRONMENT.strip().lower() != "production"

app = FastAPI(
    title=settings.PROJECT_NAME,
    # Never `debug=True`: the framework's debug page prints stack traces to the caller and bypasses the error
    # handler below. Tracebacks go to the logs (and Sentry) instead, whatever the DEBUG setting says.
    debug=False,
    lifespan=lifespan,
    docs_url="/docs" if _docs_on else None,
    redoc_url="/redoc" if _docs_on else None,
    openapi_url="/openapi.json" if _docs_on else None,
)


_CONNECTION_HINTS = ("connect", "timeout", "timed out", "server closed", "ssl", "terminating connection", "network")


def is_database_unavailable(exc: BaseException) -> bool:
    """True for "could not get / keep a database connection" failures: a pool that stayed exhausted past
    DB_POOL_TIMEOUT_SECONDS, a connect that timed out, a connection the server dropped. Not for SQL errors."""
    if isinstance(exc, (SATimeoutError, DisconnectionError)):
        return True
    if isinstance(exc, OperationalError):
        return bool(exc.connection_invalidated) or any(h in str(exc).lower() for h in _CONNECTION_HINTS)
    return False


@app.exception_handler(SATimeoutError)
@app.exception_handler(DisconnectionError)
@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """The database could not be reached in time: a temporary 503 (clients may retry reads), not a bug-shaped 500."""
    if not is_database_unavailable(exc):
        return await unhandled_error(request, exc)
    rid = request_id_var.get()
    log.error("Database unavailable on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(
        {"detail": "The server is busy right now. Please try again in a few seconds.", "request_id": rid},
        status_code=503,
        headers={"X-Request-ID": rid, "Retry-After": "5"},
    )


@app.exception_handler(DuplicatePurchase)
async def duplicate_purchase(request: Request, exc: DuplicatePurchase) -> JSONResponse:
    """A cash purchase that looks like an earlier one: nothing was saved. `detail` is plain text (older apps show it as the error);
    newer apps read `code` and `matches` to ask the person whether it is the same purchase or a different one."""
    return JSONResponse({"detail": exc.message, "code": "POSSIBLE_DUPLICATE", "matches": exc.matches}, status_code=409)


@app.exception_handler(StorageUnavailable)
async def storage_unavailable(request: Request, exc: StorageUnavailable) -> JSONResponse:
    """The file store did not confirm a write. Nothing was saved and no record was created, so a retry is always safe."""
    rid = request_id_var.get()
    log.error("File storage unavailable on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        {"detail": "The file could not be saved right now and nothing was recorded. Please try again in a moment.", "request_id": rid},
        status_code=503,
        headers={"X-Request-ID": rid, "Retry-After": "5"},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything we did not anticipate: log it with its request id, tell the caller only that id."""
    rid = request_id_var.get()
    log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        {"detail": "Something went wrong on our side. Please try again — if it keeps happening, quote this reference.", "request_id": rid},
        status_code=500,
        headers={"X-Request-ID": rid},
    )


# add_middleware: the LAST one added is the OUTERMOST. Request flow:
#   request id/log -> CORS -> rate limit -> body limit -> security headers -> gzip -> app
# CORS sits outside the rate limiter so a 429 still carries CORS headers and the browser can read it.
app.add_middleware(SelectiveGZip)
app.add_middleware(CacheInvalidationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Card-Count", "X-Vendor-Count", "Retry-After"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/count", include_in_schema=False)
def direct_qr_count(
    request: Request,
    s: str | None = None,
    sig: str | None = None,
    db: Session = Depends(get_db),
):
    """Direct handler for scans hitting the backend:
    - If the backend is running separately from the frontend SPA, redirect the browser to the frontend SPA's /count URL.
    - If accessed directly or frontend is co-hosted, render a clean branded HTML count card directly.
    """
    public_url = (settings.PUBLIC_APP_URL or "").strip().rstrip("/")
    s_clean = (s or "").strip()
    sig_clean = (sig or "").strip()

    req_host = request.headers.get("host") or ""
    should_redirect = False
    if public_url and s_clean and sig_clean:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(public_url)
            if parsed.netloc and parsed.netloc != req_host:
                should_redirect = True
        except Exception:
            pass

    if should_redirect:
        return RedirectResponse(
            url=f"{public_url}/count?s={s_clean}&sig={sig_clean}",
            status_code=307,
        )

    # Standalone HTML fallback rendering
    if not s_clean or not sig_clean:
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Veekay Bottle Count</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eaf3fa; margin: 0; padding: 0; color: #1e293b; }
    .header { background: #0B6FB8; color: white; padding: 12px; text-align: center; font-weight: 700; font-size: 14px; letter-spacing: 1px; }
    .card { max-width: 420px; margin: 32px auto; background: white; border-radius: 16px; padding: 28px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
    h2 { font-size: 18px; margin: 0 0 8px; color: #0f172a; }
    p { color: #64748b; font-size: 14px; margin: 0; }
  </style>
</head>
<body>
  <div class="header">VEE KAY AQUATECH PVT. LTD.</div>
  <div class="card">
    <h2>Invalid QR Code</h2>
    <p>Missing store identification or signature parameters. Please scan the QR code printed on the physical Veekay card again.</p>
  </div>
</body>
</html>""",
            status_code=400,
        )

    try:
        store_uuid = uuid.UUID(s_clean)
    except ValueError:
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Veekay Bottle Count</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eaf3fa; margin: 0; padding: 0; color: #1e293b; }
    .header { background: #0B6FB8; color: white; padding: 12px; text-align: center; font-weight: 700; font-size: 14px; letter-spacing: 1px; }
    .card { max-width: 420px; margin: 32px auto; background: white; border-radius: 16px; padding: 28px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
    h2 { font-size: 18px; margin: 0 0 8px; color: #0f172a; }
    p { color: #64748b; font-size: 14px; margin: 0; }
  </style>
</head>
<body>
  <div class="header">VEE KAY AQUATECH PVT. LTD.</div>
  <div class="card">
    <h2>Invalid QR Code Format</h2>
    <p>The scanned store identifier is not formatted properly. Please scan the code printed on your Veekay card again.</p>
  </div>
</body>
</html>""",
            status_code=400,
        )

    try:
        data = card_service.public_count(db, store_uuid, sig_clean)
    except Exception:
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Veekay Bottle Count</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eaf3fa; margin: 0; padding: 0; color: #1e293b; }
    .header { background: #0B6FB8; color: white; padding: 12px; text-align: center; font-weight: 700; font-size: 14px; letter-spacing: 1px; }
    .card { max-width: 420px; margin: 32px auto; background: white; border-radius: 16px; padding: 28px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
    h2 { font-size: 18px; margin: 0 0 8px; color: #0f172a; }
    p { color: #64748b; font-size: 14px; margin: 0; }
  </style>
</head>
<body>
  <div class="header">VEE KAY AQUATECH PVT. LTD.</div>
  <div class="card">
    <h2>Invalid or Tampered QR Code</h2>
    <p>This QR code could not be verified or the store is no longer active. Please scan the code printed on your physical Veekay card again.</p>
  </div>
</body>
</html>""",
            status_code=404,
        )

    store_name = html.escape(data.get("store_name") or "Store")
    store_code = html.escape(data.get("store_code") or "")
    vendor_name = html.escape(data.get("vendor_name") or "")
    cur_label = html.escape(data.get("this_month_label") or "This Month")
    cur_bottles = int(data.get("this_month_bottles") or 0)
    has_last = bool(data.get("last_month_label"))
    last_label = html.escape(data.get("last_month_label") or "")
    last_bottles = int(data.get("last_month_bottles") or 0)
    as_on_str = html.escape(data.get("as_on").strftime("%d %b %Y, %I:%M %p UTC") if data.get("as_on") else "")

    last_month_html = ""
    if has_last:
        last_month_html = f"""
        <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e8f0;">
          <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase;">Last Month &mdash; {last_label}</div>
          <div style="font-size: 40px; font-weight: 800; color: #084B7C; margin: 4px 0;">{last_bottles}</div>
          <div style="font-size: 12px; color: #64748b;">bottles supplied (full month)</div>
        </div>
        """

    vendor_line = f" &middot; Vendor: <b>{vendor_name}</b>" if vendor_name else ""

    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{store_name} - Bottle Supply Status</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #eaf3fa; margin: 0; padding: 0; color: #1e293b; }}
    .header {{ background: #0B6FB8; color: white; padding: 12px; text-align: center; font-weight: 700; font-size: 14px; letter-spacing: 1px; }}
    .container {{ max-width: 440px; margin: 20px auto; padding: 0 16px 40px; }}
    .card {{ background: white; border-radius: 20px; padding: 24px; text-align: center; box-shadow: 0 6px 20px rgba(11, 111, 184, 0.08); border: 1px solid #dbeafe; }}
    .meta-tag {{ display: inline-block; background: #e8f2fa; color: #084B7C; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 700; margin-bottom: 12px; }}
    .store-title {{ font-size: 20px; font-weight: 800; color: #0f172a; margin: 4px 0 6px; line-height: 1.3; }}
    .store-sub {{ font-size: 13px; color: #64748b; margin-bottom: 20px; }}
    .stat-box {{ background: #f8fafc; border-radius: 16px; padding: 20px; border: 1px solid #e2e8f0; }}
    .count-number {{ font-size: 56px; font-weight: 800; color: #0B6FB8; line-height: 1; margin: 8px 0; }}
    .footer-note {{ font-size: 11px; color: #94a3b8; margin-top: 18px; }}
  </style>
</head>
<body>
  <div class="header">VEE KAY AQUATECH PVT. LTD.</div>
  <div class="container">
    <div class="card">
      <div class="meta-tag">Verified Store Card</div>
      <h1 class="store-title">{store_name}</h1>
      <div class="store-sub">Store ID: <b>{store_code}</b>{vendor_line}</div>

      <div class="stat-box">
        <div style="font-size: 12px; font-weight: 700; color: #0B6FB8; text-transform: uppercase;">{cur_label} &bull; Till Date</div>
        <div class="count-number">{cur_bottles}</div>
        <div style="font-size: 13px; font-weight: 600; color: #64748b;">bottles supplied</div>
      </div>

      {last_month_html}

      <div class="footer-note">As on {as_on_str}</div>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_page, status_code=200)
