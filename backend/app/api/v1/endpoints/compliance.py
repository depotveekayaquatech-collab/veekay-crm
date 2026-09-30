"""Compliance cards & bills, and the accountant's due-alerts / search."""
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.compliance import (
    ComplianceStorePage, DocBrief, DownloadRequest, DueBills, SearchPage,
)
from app.services import compliance_service

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _has_any(perms: set[str], *codes: str) -> bool:
    return any(c in perms for c in codes)


def _require_any(perms: set[str], *codes: str) -> None:
    from fastapi import HTTPException, status
    if not _has_any(perms, *codes):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to do that.")


@router.get("/stores", response_model=ComplianceStorePage)
def stores(
    month: str | None = None,
    partner: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ComplianceStorePage:
    """Stores (yours, or all for admins) with this month's card / bill status."""
    _require_any(perms, "compliance.upload", "compliance.manage")
    return compliance_service.list_stores(
        db, user, perms, month_str=month, partner=partner, q=q, page=page, page_size=page_size
    )


@router.post("/upload", response_model=DocBrief)
async def upload(
    store_id: uuid.UUID = Form(...),
    month: str = Form(...),
    kind: str = Form(...),
    files: list[UploadFile] = File(...),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocBrief:
    """One file is stored as-is; 2+ photos are merged into one PDF; a PDF goes alone."""
    _require_any(perms, "compliance.upload", "compliance.manage")
    cap = settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024 + 1
    blobs = [(f.filename or "file", await f.read(cap)) for f in files]
    return compliance_service.upload(db, user, perms, store_id, month, kind, blobs)


@router.delete("/{doc_id}", status_code=204)
def remove(
    doc_id: uuid.UUID,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    _require_any(perms, "compliance.upload", "compliance.manage")
    compliance_service.remove(db, user, perms, doc_id)
    return Response(status_code=204)


@router.get("/search", response_model=SearchPage, dependencies=[Depends(require_permission("accounts.view"))])
def search(
    month: str | None = None,
    partner: str | None = None,
    entity: str | None = None,
    state: str | None = None,
    city: str | None = None,
    vendor: str | None = None,
    q: str | None = None,
    kind: str = Query("any", pattern="^(any|card|bill|both)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchPage:
    return compliance_service.search(
        db, user, month_str=month, partner=partner, entity=entity, state=state, city=city,
        vendor=vendor, q=q, kind=kind, page=page, page_size=page_size,
    )


@router.get("/due", response_model=DueBills, dependencies=[Depends(require_permission("accounts.view"))])
def due(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DueBills:
    """Pending bills whose due date has arrived, most overdue first."""
    return compliance_service.due_bills(db, user)


@router.post("/download")
def download(
    payload: DownloadRequest,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    data = compliance_service.zip_docs(db, user, perms, payload.ids)
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="documents.zip"'},
    )


@router.post("/{doc_id}/clear", response_model=DocBrief, dependencies=[Depends(require_permission("accounts.clear"))])
def clear(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocBrief:
    return compliance_service.clear_bill(db, user, doc_id)


@router.get("/{doc_id}/file")
def file(
    doc_id: uuid.UUID,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Authenticated file view (inline). Employees: own stores only; accountants/admins: any."""
    data, content_type, name = compliance_service.read_file(db, user, perms, doc_id)
    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff"},
    )
