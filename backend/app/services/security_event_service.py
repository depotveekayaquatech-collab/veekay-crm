"""The security-event log: refused cross-scope attempts and sensitive changes (role assignments), kept apart from the entry history so a refusal is never
mistaken for a change. Written on its own connection and committed at once, so it survives the request failing (same idea as the mark journal).
Append-only: the database refuses UPDATE / DELETE / TRUNCATE. Never raises."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from app.core.logging_config import request_id_var
from app.db.session import engine
from app.models.user import User

log = logging.getLogger("app.security")


def record(
    actor: User | None, event_type: str, *, target_type: str | None = None, target_id: object = None, detail: dict | None = None,
    ip: str | None = None, role: str | None = None,
) -> None:
    import json

    rid = request_id_var.get()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO security_events (organization_id, actor_user_id, actor_name, actor_code, actor_role, event_type, target_type, "
                    "target_id, detail, request_id, ip) VALUES (:org, :uid, :name, :code, :role, :etype, :ttype, :tid, CAST(:detail AS jsonb), :rid, :ip)"
                ),
                {
                    "org": actor.organization_id if actor else None, "uid": actor.id if actor else None,
                    "name": actor.full_name if actor else None, "code": actor.employee_code if actor else None, "role": role,
                    "etype": event_type, "ttype": target_type, "tid": None if target_id is None else str(target_id),
                    "detail": json.dumps(detail, default=str) if detail is not None else None, "rid": None if rid == "-" else rid, "ip": ip,
                },
            )
    except Exception:  # noqa: BLE001 - the log must never break the request it is describing
        log.exception("could not write a security event (%s)", event_type)
