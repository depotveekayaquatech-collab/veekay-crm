"""
File storage for compliance cards and bills.

Local-disk implementation behind three functions (save / read / delete). To move
to S3 or Drive later, replace only this file — callers only ever see "keys".
Keys are relative paths; every path is resolved under the storage root and
rejected if it would escape it.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9 ._()&+-]+")


def safe_segment(value: str | None, fallback: str = "Unknown") -> str:
    """One folder/file name component: no separators, dots-only or traversal."""
    cleaned = _SAFE.sub("_", (value or "").strip()).strip(" .")
    return cleaned[:80] or fallback


def _root() -> Path:
    root = Path(settings.UPLOAD_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    return root.resolve()


def _path(key: str) -> Path:
    root = _root()
    p = (root / key).resolve()
    if root != p and root not in p.parents:
        raise ValueError("Invalid storage key.")
    return p


def save(key: str, data: bytes) -> None:
    p = _path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(p)  # atomic on the same volume


def read(key: str) -> bytes:
    return _path(key).read_bytes()


def exists(key: str) -> bool:
    try:
        return _path(key).is_file()
    except ValueError:
        return False


def delete(key: str) -> None:
    """Best effort — a missing file is not an error."""
    try:
        _path(key).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
