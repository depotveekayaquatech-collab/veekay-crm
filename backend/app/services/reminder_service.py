"""
Bill-due reminders for the vendors and POCs of a store, sent by the daily 10:00 job.

A bill that is unpaid gets a reminder at each stage, once: 3 days before it is due ("soon"), around the due date ("due"),
then when it is 7, 14 and 30 days late. `bill_reminders` remembers what was sent, so running the job twice, or late, never
repeats a message, and a bill that is already very late when the job first runs gets one message, not four.
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.compliance_document import BillStatus, ComplianceDocument, DocKind
from app.models.external_activity import BillReminder
from app.services import external_notify

log = logging.getLogger("veekay.reminders")


def stage_for(days_until_due: int) -> str | None:
    """Which reminder a bill is in today (None = too early to remind). Negative = days late."""
    if days_until_due > 3:
        return None
    if days_until_due >= 1:
        return "soon"
    if days_until_due >= -6:
        return "due"
    if days_until_due >= -13:
        return "late7"
    if days_until_due >= -29:
        return "late14"
    return "late30"


def _wording(stage: str, days_until_due: int) -> str:
    return {
        "soon": f"Bill due in {days_until_due} day{'s' if days_until_due != 1 else ''}",
        "due": "Bill is due" if days_until_due == 0 else f"Bill was due {-days_until_due} day{'s' if days_until_due != -1 else ''} ago",
        "late7": "Bill is a week late",
        "late14": "Bill is two weeks late",
        "late30": "Bill is over a month late",
    }[stage]


def send_bill_reminders(db: Session, today: date | None = None) -> dict:
    """Notifies the people linked to each store whose pending bill reached a new stage. Commits."""
    today = today or date.today()
    docs = db.execute(
        select(ComplianceDocument).options(joinedload(ComplianceDocument.store)).where(
            ComplianceDocument.kind == DocKind.BILL.value, ComplianceDocument.status == BillStatus.PENDING.value,
            ComplianceDocument.deleted_at.is_(None), ComplianceDocument.due_date.is_not(None),
            ComplianceDocument.due_date <= date.fromordinal(today.toordinal() + 3),
        )
    ).scalars().all()
    if not docs:
        return {"bills": 0, "reminders": 0, "people": 0}
    sent_before = {(d, s) for d, s in db.execute(select(BillReminder.document_id, BillReminder.stage).where(BillReminder.document_id.in_([d.id for d in docs])))}
    reminders = people = 0
    for d in docs:
        days = (d.due_date - today).days
        stage = stage_for(days)
        if stage is None or (d.id, stage) in sent_before:
            continue
        n = external_notify.notify_store(
            db, d.store_id, kind="bill", ref_id=d.id,
            title=f"{_wording(stage, days)}: {d.month:%B %Y}", body=f"{d.store.name} · due {d.due_date:%d %b %Y}",
        )
        db.add(BillReminder(document_id=d.id, stage=stage))
        reminders += 1
        people += n
    db.commit()
    if reminders:
        log.info("bill reminders: %d bill(s), %d notification(s)", reminders, people)
    return {"bills": len(docs), "reminders": reminders, "people": people}
