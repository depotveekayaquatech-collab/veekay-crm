import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.test_report import TestReportOut, TestReportOverview
from app.services import test_report_service

router = APIRouter(prefix="/test-reports", tags=["test-reports"])


@router.get(
    "", response_model=TestReportOverview,
    dependencies=[Depends(require_permission("orders.overview"))],
)
def overview(
    partner: str = Query("zepto", description="Platform slug"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TestReportOverview:
    """Per-state test reports for a platform, with six-month validity status and the totals used for alerts."""
    return test_report_service.overview(db, user, partner)


@router.post(
    "", response_model=TestReportOut, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("compliance.manage"))],
)
async def upload(
    partner: str = Form(...),
    state: str = Form(...),
    period_start: str = Form(..., description="YYYY-MM: the month the 6-month period starts in"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TestReportOut:
    data = await file.read(settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024 + 1)
    return test_report_service.upload(db, user, partner, state, period_start, file.filename or "", data)


@router.delete(
    "/{report_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("compliance.manage"))],
)
def remove(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    test_report_service.remove(db, user, report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{report_id}/url", dependencies=[Depends(require_permission("orders.overview"))])
def file_url(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Short-lived direct link to the stored file (null on local-disk storage: use /file)."""
    return test_report_service.file_link(db, user, report_id)


@router.get("/{report_id}/file", dependencies=[Depends(require_permission("orders.overview"))])
def file(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    data, content_type, name = test_report_service.read_file(db, user, report_id)
    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store"},
    )
