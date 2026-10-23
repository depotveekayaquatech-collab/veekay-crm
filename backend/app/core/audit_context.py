"""Who is making this change? Carried into the database so the triggers on order_entries can stamp ownership and write the audit trail.

The authenticated user (taken from the verified token, never from the request body) is attached to the SQLAlchemy session; every transaction
the session begins re-applies it with `set_config(..., is_local => true)`, so it cannot leak to another request on the same pooled
connection, and a commit in the middle of a request does not lose it. Per-call details (the reason for a correction, a review comment, the
client's idempotency key) are set with `bind(...)` right before the write and forgotten when the transaction ends.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.logging_config import request_id_var

KEYS = ("actor_id", "reason", "comment", "request_id", "source", "request_key", "client", "client_time", "keep_creator", "event_type")
TRANSIENT = ("reason", "comment", "request_key", "client_time", "keep_creator", "event_type")
_SAFE = re.compile(r"[^A-Za-z0-9._/ :+-]")
def current_client(db: Session) -> str | None:
    """Where the request being served came from (used by the mark journal). Kept on the session: dependencies and endpoints run in different
    threads, so a context variable would not reach the endpoint."""
    return (db.info.get("audit_ctx") or {}).get("client")


def _apply(connection, ctx: dict[str, Any]) -> None:
    connection.exec_driver_sql(
        "SELECT " + ", ".join("set_config(%s, %s, true)" for _ in KEYS),
        tuple(v for k in KEYS for v in (f"app.{k}", "" if ctx.get(k) is None else str(ctx[k]))),
    )


@event.listens_for(Session, "after_begin")
def _on_begin(session: Session, transaction, connection) -> None:           # noqa: ARG001
    ctx = session.info.get("audit_ctx")
    if ctx:
        _apply(connection, ctx)


@event.listens_for(Session, "after_transaction_end")
def _on_end(session: Session, transaction) -> None:                         # noqa: ARG001
    ctx = session.info.get("audit_ctx")
    if ctx and transaction.parent is None:                                  # the outermost transaction ended: per-call details are spent
        for k in TRANSIENT:
            ctx.pop(k, None)


def client_label(request: Request | None) -> str:
    """Where the call came from, for the audit trail: the app says so itself (X-Client); otherwise guessed from the user agent."""
    if request is None:
        return "server"
    declared = request.headers.get("x-client", "").strip()
    if declared:
        return _SAFE.sub("", declared)[:60] or "unknown"
    ua = request.headers.get("user-agent", "").lower()
    if "okhttp" in ua or "expo" in ua or "reactnative" in ua or "dalvik" in ua:
        return "android_app"
    if ua:
        return "web_crm"
    return "unknown"


def bind(db: Session, actor=None, **details: Any) -> None:
    """Attach the actor and/or per-call details to this session, effective immediately and for every later transaction of the session."""
    ctx = db.info.setdefault("audit_ctx", {})
    if actor is not None:
        ctx["actor_id"] = str(actor.id)
    ctx.setdefault("request_id", request_id_var.get() if request_id_var.get() != "-" else None)
    for k, v in details.items():
        ctx[k] = v
    _apply(db.connection(), ctx)


def bind_request(db: Session, actor, request: Request | None) -> None:
    """Called once per authenticated request: the actor, the request id and where the call came from."""
    source = client_label(request)
    bind(db, actor, source=source, client=source, request_id=request_id_var.get() if request_id_var.get() != "-" else None)

