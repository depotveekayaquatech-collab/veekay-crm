"""Photo handling for the vendor / POC app: validate, strip metadata, downscale, store."""
import io
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status

from app.core import storage
from app.core.config import settings

MAX_PHOTOS = 5
MAX_DIMENSION = 2000
MAX_PIXELS = 60_000_000


@dataclass
class Photo:
    name: str
    data: bytes           # re-encoded JPEG


def _bad(detail: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(code, detail)


def read_photos(files: list[UploadFile] | None) -> list[Photo]:
    """Real images only (checked by decoding, not by file name). Re-encoded as JPEG without EXIF / GPS data."""
    from PIL import Image, ImageOps

    files = [f for f in (files or []) if f and f.filename]
    if len(files) > MAX_PHOTOS:
        raise _bad(f"Attach at most {MAX_PHOTOS} photos.")
    limit = settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    out: list[Photo] = []
    for f in files:
        raw = f.file.read(limit + 1)
        if not raw:
            raise _bad(f"'{f.filename}' is empty.")
        if len(raw) > limit:
            raise _bad(f"'{f.filename}' is larger than {settings.COMPLIANCE_MAX_FILE_MB} MB.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=85)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise _bad(f"'{f.filename}' is not a photo we can read.") from exc
        out.append(Photo(name=(f.filename or "photo").rsplit("/", 1)[-1][:120], data=buf.getvalue()))
    return out


def store_photo(ticket_id: uuid.UUID, photo: Photo) -> tuple[str, str, int]:
    """Writes the photo to storage; returns (key, file_name, size)."""
    key = f"Tickets/{ticket_id}/{uuid.uuid4().hex}.jpg"
    storage.save(key, photo.data)
    stem = photo.name.rsplit(".", 1)[0] or "photo"
    return key, f"{stem}.jpg", len(photo.data)
