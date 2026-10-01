"""
Logging: one line per request and per error, tagged with a request id.

Production emits JSON lines (easy to search in Render / Datadog / Loki); development
prints readable text. The request id also comes back to the caller in the `X-Request-ID`
header and in the body of a 500, so "it broke at 3pm" can be matched to a log line.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_EXTRA_FIELDS = ("method", "path", "status", "ms", "ip", "bytes")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if settings.RELEASE:
            out["release"] = settings.RELEASE
        for f in _EXTRA_FIELDS:
            if hasattr(record, f):
                out[f] = getattr(record, f)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def use_json() -> bool:
    return settings.LOG_JSON if settings.LOG_JSON is not None else settings.ENVIRONMENT.strip().lower() == "production"


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        JsonFormatter() if use_json() else logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    logging.getLogger("uvicorn.access").disabled = True      # replaced by our own one-line-per-request log
    logging.getLogger("uvicorn.error").handlers[:] = []      # let it propagate to the root handler
    logging.getLogger("uvicorn.error").propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
