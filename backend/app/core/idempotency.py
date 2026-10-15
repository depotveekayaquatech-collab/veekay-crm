"""
Replay-safe create requests.

    key = idempotency_key_header(...)            # FastAPI dependency: the optional `Idempotency-Key` header
    return run_once(db, owner=str(account.id), endpoint="external.ticket.create", key=key, produce=lambda: do_create())

  * No key: `produce()` just runs (existing behaviour, nothing stored).
  * First request with a key: the key is reserved (committed), `produce()` runs, its response is stored.
  * The same key again: the stored response is returned and NOTHING is created a second time, even if the first request
    timed out on the phone after the server had already saved it.
  * Same key while the first is still running: 409 "still being processed" (the client retries shortly).
  * `produce()` fails: the reservation is removed, so the retry runs normally.

Known limit: if the server dies between saving the record and storing the response (a window of milliseconds), the
reservation stays "pending" and a retry after STALE_AFTER_SECONDS creates the record again. Deliberately accepted.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey

STALE_AFTER_SECONDS = 120
KEEP_DAYS = 3
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")


def idempotency_key_header(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str | None:
    """The optional header. A malformed value is a client bug: reject it instead of silently disabling the protection."""
    if idempotency_key is None or idempotency_key == "":
        return None
    if not _KEY.match(idempotency_key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Idempotency-Key must be 8-80 characters: letters, digits, - _ . :")
    return idempotency_key


def _find(db: Session, owner: str, endpoint: str, key: str) -> IdempotencyKey | None:
    return db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.owner == owner, IdempotencyKey.endpoint == endpoint, IdempotencyKey.key == key
        )
    ).scalar_one_or_none()


def run_once(db: Session, *, owner: str, endpoint: str, key: str | None, produce: Callable[[], BaseModel]):
    if key is None:
        return produce()

    now = datetime.now(timezone.utc)
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < now - timedelta(days=KEEP_DAYS)))
    try:
        db.add(IdempotencyKey(owner=owner, endpoint=endpoint, key=key, state="pending"))
        db.commit()
    except IntegrityError:
        db.rollback()
        row = _find(db, owner, endpoint, key)
        if row is None:  # purged between the two statements: just try again
            return run_once(db, owner=owner, endpoint=endpoint, key=key, produce=produce)
        if row.state == "done" and row.response is not None:
            return row.response
        age = now - row.created_at
        if age < timedelta(seconds=STALE_AFTER_SECONDS):
            raise HTTPException(status.HTTP_409_CONFLICT, "This request is still being processed. Try again in a moment.") from None
        row.created_at = now   # an abandoned reservation: take it over
        db.commit()

    try:
        result = produce()
    except BaseException:
        db.rollback()
        db.execute(delete(IdempotencyKey).where(
            IdempotencyKey.owner == owner, IdempotencyKey.endpoint == endpoint, IdempotencyKey.key == key))
        db.commit()
        raise

    row = _find(db, owner, endpoint, key)
    if row is not None:
        row.state = "done"
        row.response = result.model_dump(mode="json")
        db.commit()
    return result
