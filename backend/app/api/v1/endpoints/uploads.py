"""The upload rules, so the web app can warn and shrink photos BEFORE sending. The server enforces them regardless."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadPolicy(BaseModel):
    photo_max_stored_kb: int      # a stored photo is never larger than this (the server shrinks it to fit)
    photo_max_upload_mb: int      # the largest raw file the server will accept
    pdf_max_mb: int               # a PDF is stored as it is, so this is a hard limit
    max_dimension: int            # longest side of a stored photo, in pixels
    jpeg_quality: int             # 1-100
    keep_below_kb: int            # a photo this small is not recompressed


@router.get("/policy", response_model=UploadPolicy)
def policy(_: User = Depends(get_current_user)) -> UploadPolicy:
    return UploadPolicy(
        photo_max_stored_kb=settings.PHOTO_MAX_STORED_KB, photo_max_upload_mb=settings.COMPLIANCE_MAX_FILE_MB,
        pdf_max_mb=settings.PDF_MAX_FILE_MB, max_dimension=settings.IMAGE_MAX_DIMENSION,
        jpeg_quality=settings.IMAGE_JPEG_QUALITY, keep_below_kb=settings.IMAGE_KEEP_BELOW_KB,
    )
