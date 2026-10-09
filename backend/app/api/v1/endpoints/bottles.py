"""Bottle QR codes: generate + print, scan IN / OUT, replace damaged codes, and the overdue (possibly lost) list."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.bottle import (
    BatchDeleteRequest, BatchOut, BottleDetail, DeleteRequest, DeleteResult, BottleList, BottleOut, GenerateRequest, ReasonBody, ReplaceResult, ScanRequest, ScanResult, Summary,
)
from app.services import bottle_service as svc

router = APIRouter(prefix="/bottles", tags=["bottles"])


def _any_of(*codes: str):
    def checker(user: User = Depends(get_current_user), permissions: set[str] = Depends(get_current_permissions)) -> User:
        if not permissions & set(codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to access this.")
        return user

    return checker


# The developer (bottles.delete) can look codes up too, so they can find what to delete.
require_viewer = _any_of("bottles.view", "bottles.delete")
require_any_bottle_access = _any_of("bottles.scan", "bottles.view", "bottles.delete")
require_manage_or_delete = _any_of("bottles.manage", "bottles.delete")

_NO_STORE = {"Cache-Control": "private, no-store"}


@router.get("/stores")
def stores(user: User = Depends(require_any_bottle_access), db: Session = Depends(get_db)) -> list[dict]:
    """Live stores to scan against (anyone who can scan or view bottles; no store permission needed)."""
    return svc.scan_stores(db, user)


@router.get("/summary", response_model=Summary)
def summary(user: User = Depends(require_viewer), db: Session = Depends(get_db)) -> Summary:
    return svc.summary(db, user)


@router.get("", response_model=BottleList)
def search(
    q: str | None = Query(None, max_length=40), state: Literal["UNUSED", "AT_STORE", "RETURNED", "RETIRED", "DELETED", "OVERDUE"] | None = None,
    store_id: uuid.UUID | None = None, overdue_days: int | None = Query(None, ge=0, le=3650),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_viewer), db: Session = Depends(get_db),
) -> BottleList:
    return svc.search(db, user.organization_id, q=q, state=state, store_id=store_id, overdue_days=overdue_days, page=page, page_size=page_size)


@router.post("/scan", response_model=ScanResult)
def scan(body: ScanRequest, user: User = Depends(require_permission("bottles.scan")), db: Session = Depends(get_db)) -> ScanResult:
    """Record one IN or OUT scan. Out-of-order scans are still recorded and come back with a `warning`."""
    store = svc.find_store(db, user.organization_id, store_id=body.store_id) if body.store_id else None
    return svc.scan(
        db, user.organization_id, serial=body.serial, direction=body.direction, store=store, scanned_at=body.scanned_at,
        scan_id=body.scan_id, source="app", user=user,
    )


@router.get("/lookup/{serial}", response_model=BottleDetail)
def lookup(serial: str, user: User = Depends(require_viewer), db: Session = Depends(get_db)) -> BottleDetail:
    """One bottle with its full scan history."""
    return svc.detail(db, user.organization_id, serial)


# ---- generate / print (bottles.manage) --------------------------------------------------------------------------

@router.post("/batches", response_model=BatchOut, status_code=201)
def generate(body: GenerateRequest, user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db)) -> BatchOut:
    """Creates `quantity` new unique QR codes. Then download the labels (PDF) or the serial list (CSV)."""
    return svc.generate_batch(db, user, body.quantity, body.note)


@router.get("/batches", response_model=list[BatchOut])
def batches(user: User = Depends(require_manage_or_delete), db: Session = Depends(get_db)) -> list[BatchOut]:
    return svc.list_batches(db, user)


@router.get("/batches/{batch_id}/labels.pdf")
def batch_labels(
    batch_id: uuid.UUID, start: int = Query(1, ge=1), count: int = Query(svc.MAX_LABELS_PER_PDF, ge=1, le=svc.MAX_LABELS_PER_PDF),
    user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db),
) -> Response:
    """Printable label sheet (40 per A4 page). A big batch is printed in ranges: ?start=1&count=2000, ?start=2001 ..."""
    return Response(
        svc.labels_pdf(db, user, batch_id, start, count), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bottle-labels-{start}.pdf"', **_NO_STORE},
    )


@router.get("/batches/{batch_id}/serials.csv")
def batch_serials(batch_id: uuid.UUID, user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db)) -> Response:
    return Response(
        svc.batch_csv(db, user, batch_id), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bottle-serials.csv"', **_NO_STORE},
    )


# ---- replace / retire (bottles.manage) --------------------------------------------------------------------------

@router.post("/{serial}/replace", response_model=ReplaceResult)
def replace(serial: str, body: ReasonBody, user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db)) -> ReplaceResult:
    """The QR is damaged: retire this code and issue a new one that carries on from where the bottle is."""
    result, _ = svc.replace(db, user, serial, body.reason)
    return result


@router.get("/{serial}/label.pdf")
def label(serial: str, user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db)) -> Response:
    """The label for one code (e.g. the replacement just issued)."""
    b = svc.detail(db, user.organization_id, serial).bottle
    return Response(svc.replacement_label_pdf(b.serial), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{b.serial}.pdf"', **_NO_STORE})


@router.post("/{serial}/retire", response_model=BottleOut)
def retire(serial: str, body: ReasonBody, user: User = Depends(require_permission("bottles.manage")), db: Session = Depends(get_db)) -> BottleOut:
    """Write a bottle off (destroyed / confirmed lost). Its code can't be scanned any more."""
    return svc.retire(db, user, serial, body.reason)


# ---- delete (history kept): developer only (reserved `bottles.delete`) -----------------------------------------------

@router.post("/delete", response_model=DeleteResult)
def delete_codes(body: DeleteRequest, user: User = Depends(require_permission("bottles.delete")), db: Session = Depends(get_db)) -> DeleteResult:
    """Deletes these codes: they can never be scanned or used again, but the records and their scan history stay on file."""
    return svc.delete_serials(db, user, body.serials, body.reason)


@router.post("/batches/{batch_id}/delete", response_model=DeleteResult)
def delete_batch(batch_id: uuid.UUID, body: BatchDeleteRequest, user: User = Depends(require_permission("bottles.delete")), db: Session = Depends(get_db)) -> DeleteResult:
    """Deletes a batch's never-used codes (history kept). Codes already scanned are left alone and listed back."""
    return svc.delete_batch(db, user, batch_id, body.reason)
