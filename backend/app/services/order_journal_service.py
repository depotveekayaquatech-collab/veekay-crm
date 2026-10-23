"""
The journal of every number an employee tries to mark, and what an admin does about the ones that were not saved.

A mark can be refused (the day already holds an imported number, the store is not assigned, the date is closed...). Before, only the error
was shown and the employee's number disappeared. Now every attempt is written to `order_mark_journal` in its OWN transaction (so it survives
the mark failing), and an admin sees the refused ones next to the numbers an import replaced, and can apply or dismiss them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.order_entry import EntrySource, OrderEntry
from app.models.store import Store
from app.models.user import User
from app.services import activity_service


def record(
    org_id: uuid.UUID, user_id: uuid.UUID | None, store_id: uuid.UUID, order_date: date, count: int | None, outcome: str,
    reason: str | None = None, *, action: str = "mark", request_key: str | None = None, client: str | None = None,
) -> None:
    """Write one attempt. Its own connection and commit: it must survive whatever happens to the mark's transaction. Never raises."""
    record_many([(org_id, user_id, store_id, order_date, count, outcome, reason, action, request_key, client)])


def record_many(rows: list[tuple]) -> None:
    if not rows:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO order_mark_journal (organization_id, user_id, store_id, order_date, bottle_count, outcome, reason, action, request_key, client) "
                    "VALUES (:org, :user, :store, :day, :count, :outcome, :reason, :action, :key, :client)"
                ),
                [
                    {"org": o, "user": u, "store": s, "day": d, "count": c, "outcome": out, "reason": (r or "")[:500] or None, "action": a,
                     "key": (k or "")[:120] or None, "client": (cl or "")[:200] or None}
                    for (o, u, s, d, c, out, r, a, k, cl) in rows
                ],
            )
    except Exception:  # noqa: BLE001 - the journal must never break the mark itself
        import logging
        logging.getLogger("app.journal").exception("could not write the order mark journal")


def open_items(db: Session, actor: User, partner_slug: str | None = None, *, days: int = 60) -> dict:
    """Numbers employees entered that were not saved, and employee numbers an import replaced: what an admin should look at."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    slug = (partner_slug or "").strip().lower() or None
    rows = db.execute(
        text("""
            SELECT j.id, j.created_at, j.order_date, j.bottle_count, j.reason, u.employee_code, u.full_name, u.id AS user_id,
                   s.id AS store_id, s.name, s.crm_code, s.external_code, o.name AS platform, e.bottle_count AS now_count, e.source AS now_source, m.full_name AS now_by
            FROM order_mark_journal j
            JOIN stores s ON s.id = j.store_id
            JOIN organizations o ON o.id = s.partner_organization_id
            LEFT JOIN users u ON u.id = j.user_id
            LEFT JOIN order_entries e ON e.store_id = j.store_id AND e.order_date = j.order_date
            LEFT JOIN users m ON m.id = e.marked_by_user_id
            WHERE j.organization_id = :org AND j.outcome = 'rejected' AND j.resolved_at IS NULL AND j.created_at >= :since
              AND (CAST(:slug AS text) IS NULL OR o.slug = :slug)
            ORDER BY j.created_at DESC LIMIT 300
        """),
        {"org": actor.organization_id, "since": since, "slug": slug},
    ).mappings().all()
    unsaved = [{
        "journal_id": str(r["id"]), "at": r["created_at"].isoformat(), "order_date": r["order_date"].isoformat(), "entered": r["bottle_count"],
        "reason": r["reason"], "employee_code": r["employee_code"], "employee_name": r["full_name"], "employee_id": str(r["user_id"]) if r["user_id"] else None,
        "store_id": str(r["store_id"]), "store_name": r["name"], "crm_code": r["crm_code"], "outlet_id": r["external_code"], "platform": r["platform"],
        "now_count": r["now_count"], "now_source": r["now_source"], "now_by": r["now_by"],
    } for r in rows]

    changed = db.execute(
        text("""
            SELECT c.id, c.changed_at, c.order_date, c.old_count, c.new_count, s.id AS store_id, s.name, s.crm_code, s.external_code, o.name AS platform
            FROM order_entry_changes c
            JOIN stores s ON s.id = c.store_id
            JOIN organizations o ON o.id = s.partner_organization_id
            JOIN order_entries e ON e.id = c.entry_id AND e.bottle_count = c.new_count
            WHERE s.organization_id = :org AND c.old_source = 'employee' AND c.new_source = 'admin' AND c.changed_at >= :since
              AND c.old_count IS NOT NULL AND c.old_count <> c.new_count AND (CAST(:slug AS text) IS NULL OR o.slug = :slug)
            ORDER BY c.changed_at DESC LIMIT 300
        """),
        {"org": actor.organization_id, "since": since, "slug": slug},
    ).mappings().all()
    replaced = [{
        "change_id": str(r["id"]), "at": r["changed_at"].isoformat(), "order_date": r["order_date"].isoformat(), "was": r["old_count"], "now": r["new_count"],
        "store_id": str(r["store_id"]), "store_name": r["name"], "crm_code": r["crm_code"], "outlet_id": r["external_code"], "platform": r["platform"],
    } for r in changed]
    return {"unsaved": unsaved, "replaced": replaced}


def apply_number(
    db: Session, actor: User, store_id: uuid.UUID, order_date: date, count: int, employee_id: uuid.UUID | None, journal_id: uuid.UUID | None = None,
) -> dict:
    """Make an employee's number the day's number (an admin's decision): the entry becomes that employee's own entry."""
    if not (settings.MIN_BOTTLE_COUNT <= count <= settings.MAX_BOTTLE_COUNT):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Bottle count must be from {settings.MIN_BOTTLE_COUNT} to {settings.MAX_BOTTLE_COUNT}.")
    if order_date > datetime.now(timezone.utc).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You can't set a future date.")
    store = db.get(Store, store_id)
    if store is None or store.organization_id != actor.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    emp = db.get(User, employee_id) if employee_id else None
    if employee_id and (emp is None or emp.organization_id != actor.organization_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    entry = db.query(OrderEntry).filter_by(store_id=store.id, order_date=order_date).one_or_none()
    was = None
    from app.core import audit_context

    audit_context.bind(db, actor, reason=f"Applied from the mark journal: the number {emp.employee_code if emp else 'an employee'} entered but that was not saved")
    if entry is None:
        db.add(OrderEntry(organization_id=actor.organization_id, store_id=store.id, order_date=order_date, bottle_count=count,
                          source=EntrySource.EMPLOYEE.value, marked_by_user_id=emp.id if emp else None))
    else:
        was = entry.bottle_count - entry.cash_adjustment
        entry.bottle_count = count + entry.cash_adjustment
        entry.source = EntrySource.EMPLOYEE.value
        entry.marked_by_user_id = emp.id if emp else None
    activity_service.record(
        db, actor=actor, action="order.employee_number_applied", entity_type="order_entry", entity_id=store.id,
        metadata={"store": store.name, "crm_code": store.crm_code, "order_date": order_date.isoformat(), "bottle_count": count, "previous": was,
                  "employee": emp.employee_code if emp else None, "journal_id": str(journal_id) if journal_id else None},
    )
    if journal_id:
        db.execute(
            text("UPDATE order_mark_journal SET resolved_at = now(), resolved_by_user_id = :by, resolution = 'applied' WHERE id = :id AND organization_id = :org AND resolved_at IS NULL"),
            {"by": actor.id, "id": journal_id, "org": actor.organization_id},
        )
    db.commit()
    return {"store_id": str(store.id), "order_date": order_date.isoformat(), "bottle_count": count, "previous": was}


def dismiss(db: Session, actor: User, journal_id: uuid.UUID) -> dict:
    n = db.execute(
        text("UPDATE order_mark_journal SET resolved_at = now(), resolved_by_user_id = :by, resolution = 'dismissed' WHERE id = :id AND organization_id = :org AND resolved_at IS NULL"),
        {"by": actor.id, "id": journal_id, "org": actor.organization_id},
    ).rowcount
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That entry was not found or is already dealt with.")
    db.commit()
    return {"dismissed": True}
