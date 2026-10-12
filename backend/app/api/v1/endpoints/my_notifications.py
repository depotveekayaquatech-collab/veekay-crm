"""A signed-in employee's own alerts (leave decided, ticket assigned, new ticket from a POC ...) and push-phone registration."""
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.external_activity import StaffDevice, StaffNotification
from app.models.user import User

router = APIRouter(prefix="/me", tags=["me"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    ref_id: str | None
    read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    page_size: int


class MarkRead(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200, description="Leave out to mark everything read.")


class DeviceIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    platform: Literal["android", "ios", "web"]


@router.get("/notifications", response_model=NotificationPage)
def notifications(
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> NotificationPage:
    mine = StaffNotification.user_id == user.id
    total = db.execute(select(func.count()).select_from(StaffNotification).where(mine)).scalar_one()
    unread = db.execute(select(func.count()).select_from(StaffNotification).where(mine, StaffNotification.read_at.is_(None))).scalar_one()
    rows = db.execute(
        select(StaffNotification).where(mine).order_by(StaffNotification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return NotificationPage(
        items=[NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, ref_id=n.ref_id, read=n.read_at is not None, created_at=n.created_at) for n in rows],
        total=total, unread=unread, page=page, page_size=page_size,
    )


@router.post("/notifications/read", status_code=204)
def mark_read(payload: MarkRead, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    stmt = update(StaffNotification).where(StaffNotification.user_id == user.id, StaffNotification.read_at.is_(None))
    if payload.ids is not None:
        stmt = stmt.where(StaffNotification.id.in_(payload.ids))
    db.execute(stmt.values(read_at=datetime.now(timezone.utc)))
    db.commit()


@router.post("/devices", status_code=204)
def register_device(payload: DeviceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Register this phone for push messages. A token that was on another login moves to this one."""
    now = datetime.now(timezone.utc)
    dev = db.execute(select(StaffDevice).where(StaffDevice.token == payload.token)).scalar_one_or_none()
    if dev is None:
        db.add(StaffDevice(user_id=user.id, token=payload.token, platform=payload.platform, last_seen_at=now))
    else:
        dev.user_id, dev.platform, dev.last_seen_at = user.id, payload.platform, now
    db.commit()


@router.delete("/devices", status_code=204)
def unregister_device(token: str = Query(..., max_length=512), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    dev = db.execute(select(StaffDevice).where(StaffDevice.token == token, StaffDevice.user_id == user.id)).scalar_one_or_none()
    if dev is not None:
        db.delete(dev)
        db.commit()
