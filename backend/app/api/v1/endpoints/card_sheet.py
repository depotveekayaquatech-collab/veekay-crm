"""Cards from an uploaded sheet. Developer-only for now (reserved `cards.sheet`), and behind an access code."""
import uuid
import datetime as dt

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import card_sheet_service as svc

router = APIRouter(prefix="/developer/card-sheet", tags=["developer"])


class UnlockBody(BaseModel):
    code: str


@router.post("/unlock")
def unlock(body: UnlockBody, user: User = Depends(require_permission("cards.sheet")), db: Session = Depends(get_db)) -> dict:
    """Checks the access code on the server. Returns a 30 minute token (sent with every later call)."""
    return svc.unlock(db, user, body.code)


@router.post("/preview")
async def preview(
    token: str = Form(...), file: UploadFile = File(...),
    user: User = Depends(require_permission("cards.sheet")), db: Session = Depends(get_db),
) -> dict:
    svc.check_token(user, token)
    parsed = svc.parse_sheet(db, user, file.filename or "", await file.read())
    return svc.preview(db, user, parsed)


@router.post("/download")
async def download(
    token: str = Form(...), file: UploadFile = File(...),
    user: User = Depends(require_permission("cards.sheet")), db: Session = Depends(get_db),
) -> Response:
    svc.check_token(user, token)
    parsed = svc.parse_sheet(db, user, file.filename or "", await file.read())
    pdf, name = svc.render(db, user, parsed)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})


class RandomRow(BaseModel):
    date: dt.date
    count: int


class RandomPdfBody(BaseModel):
    token: str
    store_id: uuid.UUID
    rows: list[RandomRow]


@router.post("/random-pdf")
def random_pdf(
    body: RandomPdfBody, user: User = Depends(require_permission("cards.sheet")), db: Session = Depends(get_db),
) -> Response:
    """Draws the standard card from rows the page generated. Render-only: nothing is stored or logged."""
    svc.check_token(user, body.token)
    pdf, name = svc.render_random(db, user, body.store_id, [(r.date, r.count) for r in body.rows])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})
