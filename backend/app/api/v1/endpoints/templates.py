"""Template sheets: a ready-made Excel file for every spreadsheet upload in the CRM, so a sheet can be shaped to the right format before it is uploaded."""
from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_current_user
from app.models.user import User
from app.services import template_service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/{kind}")
def template(kind: str, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), user: User = Depends(get_current_user)) -> Response:
    """kind: orders, employees, attendance, cash, cardsheet, stores or vendor-rates. `month` (2026-10) sets the date columns of the orders and attendance sheets."""
    data, name = template_service.make(kind, month)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, max-age=300"},
    )
