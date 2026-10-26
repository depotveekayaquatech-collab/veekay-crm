"""
Notifications for vendors / POCs: every account linked to a store gets an in-app feed entry, and a push message to
its registered phones when Firebase is configured (FIREBASE_CREDENTIALS_JSON or _FILE). Callers add this inside their own
transaction; a failing push never breaks the action that caused it.
"""
import json
import logging
import uuid
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.external_account import ExternalAccount, ExternalAccountStore
from app.models.external_activity import ExternalDevice, ExternalNotification

log = logging.getLogger("app.external_notify")


def push_configured() -> bool:
    return bool(settings.FIREBASE_CREDENTIALS_JSON or settings.FIREBASE_CREDENTIALS_FILE)


@lru_cache(maxsize=1)
def _firebase():
    """The firebase_admin messaging module, or None when push isn't set up."""
    if not push_configured():
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        firebase_admin.initialize_app(credentials.Certificate(json.loads(settings.FIREBASE_CREDENTIALS_JSON) if settings.FIREBASE_CREDENTIALS_JSON else settings.FIREBASE_CREDENTIALS_FILE))
        return messaging
    except Exception:  # missing package / bad file: stay in-app only
        log.exception("Firebase push is not available")
        return None


def _push(tokens: list[str], title: str, body: str, data: dict[str, str]) -> None:
    messaging = _firebase()
    if messaging is None or not tokens:
        return
    try:
        messaging.send_each_for_multicast(messaging.MulticastMessage(
            tokens=tokens, notification=messaging.Notification(title=title, body=body), data=data,
        ))
    except Exception:
        log.exception("Push send failed")


def notify_store(db: Session, store_id: uuid.UUID, *, kind: str, title: str, body: str, ref_id: uuid.UUID | str | None = None,
                 skip_account_id: uuid.UUID | None = None) -> int:
    """Notify every active vendor / POC linked to the store. Returns how many accounts were notified."""
    ids = [
        i for i in db.execute(
            select(ExternalAccount.id).join(ExternalAccountStore, ExternalAccountStore.account_id == ExternalAccount.id)
            .where(ExternalAccountStore.store_id == store_id, ExternalAccount.is_active.is_(True))
        ).scalars()
        if i != skip_account_id
    ]
    for account_id in ids:
        db.add(ExternalNotification(account_id=account_id, kind=kind, title=title[:160], body=body[:500], ref_id=str(ref_id) if ref_id else None))
    if ids and push_configured():
        tokens = list(db.execute(select(ExternalDevice.token).where(ExternalDevice.account_id.in_(ids))).scalars())
        _push(tokens, title, body, {"kind": kind, "ref_id": str(ref_id or "")})
    return len(ids)
