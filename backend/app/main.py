"""Application entrypoint: FastAPI app, middleware, router mounting."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core import scheduler
from app.core.config import settings
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
