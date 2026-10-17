"""
Shrink an uploaded photo before it is stored, and keep it inside the size policy.

A phone photo is 2-8 MB; a receipt or a store card only needs to stay readable when zoomed in. So a photo is
  * rotated upright (EXIF orientation applied, then the EXIF block dropped: no GPS position is kept),
  * limited to IMAGE_MAX_DIMENSION pixels on its longest side,
  * stored as JPEG (PNG only when it really has transparency),
  * and ALWAYS at most PHOTO_MAX_STORED_KB: if the first attempt is larger, quality and then size are lowered step by step
    until it fits. If it cannot be made to fit, `ImageTooLarge` is raised and nothing is stored.
An image that is already small and has no GPS data is left exactly as it is, so a file is never recompressed twice,
and an optimized result that would be BIGGER than the original is discarded in favour of the original.
PDFs are never touched here.
"""
from __future__ import annotations

import io

from app.core.config import settings

_GPS_IFD = 0x8825
MAX_PIXELS = 60_000_000
_MIN_QUALITY = 55
_MIN_DIMENSION = 900


class UnreadableImage(ValueError):
    """The bytes look like an image (the signature matched) but cannot be decoded."""


class ImageTooLarge(ValueError):
    """The photo could not be brought under the stored-size limit without making it unreadable."""


def sniff(data: bytes) -> str | None:
    """The real type from the file's first bytes (never from its name): pdf / jpg / png / webp, or None."""
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def stored_limit_bytes() -> int:
    return settings.PHOTO_MAX_STORED_KB * 1024


def _has_alpha(img) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def encode_jpeg_within_budget(img, limit_bytes: int | None = None) -> bytes:
    """JPEG bytes of `img` (already upright) that fit `limit_bytes`: IMAGE_MAX_DIMENSION / IMAGE_JPEG_QUALITY first, then lower
    quality, then smaller dimensions. Raises ImageTooLarge when even the smallest attempt does not fit."""
    from PIL import Image

    limit_bytes = limit_bytes or stored_limit_bytes()
    rgb = img.convert("RGB")
    dim, quality = settings.IMAGE_MAX_DIMENSION, settings.IMAGE_JPEG_QUALITY
    while True:
        work = rgb.copy()
        work.thumbnail((dim, dim), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        work.save(out, "JPEG", quality=quality, optimize=True)
        if out.tell() <= limit_bytes:
            return out.getvalue()
        if quality > _MIN_QUALITY:
            quality = max(_MIN_QUALITY, quality - 8)
        elif dim > _MIN_DIMENSION:
            dim = max(_MIN_DIMENSION, int(dim * 0.85))
        else:
            raise ImageTooLarge("too large")


def optimize(data: bytes, ext: str) -> tuple[bytes, str]:
    """(bytes to store, extension) for one photo. `ext` is the sniffed type: jpg / png / webp.
    Raises UnreadableImage (cannot be decoded) or ImageTooLarge (cannot fit the stored-size limit)."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    limit = settings.IMAGE_MAX_DIMENSION
    cap = stored_limit_bytes()
    try:
        img = Image.open(io.BytesIO(data))
        original_size = img.size
        exif = img.getexif()
        has_gps = bool(exif.get_ifd(_GPS_IFD)) if exif else False
        upright = exif.get(0x0112, 1) in (0, 1) if exif else True
        small = len(data) <= settings.IMAGE_KEEP_BELOW_KB * 1024 and max(original_size) <= limit
        if not settings.IMAGE_OPTIMIZE or (small and not has_gps and upright):
            img.load()                                   # still proves the file decodes
            if len(data) > cap:
                raise ImageTooLarge("too large")         # optimization is off: the policy still applies
            return data, ext
        if img.format == "JPEG":
            img.draft("RGB", (limit, limit))             # decode at a reduced size: far less memory for a 12 MP photo
        img = ImageOps.exif_transpose(img)
        new_ext = "jpg"
        if _has_alpha(img):
            flat = img.convert("RGBA")
            flat.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            flat.save(out, "PNG", optimize=True)
            if out.tell() <= cap:
                result, new_ext = out.getvalue(), "png"
            else:                                        # a transparent image that is still too big is flattened onto white
                bg = Image.new("RGB", flat.size, (255, 255, 255))
                bg.paste(flat, mask=flat.split()[3])
                result = encode_jpeg_within_budget(bg, cap)
        else:
            result = encode_jpeg_within_budget(img, cap)
    except ImageTooLarge:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise UnreadableImage(str(exc)) from exc

    if len(result) >= len(data) and len(data) <= cap and not has_gps and upright and max(original_size) <= limit:
        return data, ext                                  # nothing gained: keep the original untouched
    return result, new_ext
