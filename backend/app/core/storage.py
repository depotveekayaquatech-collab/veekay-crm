"""
File storage for compliance cards, invoices and payment proofs.

Callers only ever deal in "keys" (relative paths) through five functions:
save / read / exists / delete / healthcheck. Two backends sit behind them:

  local — a folder on the server (UPLOAD_DIR). Fine on a machine with a durable disk;
          on hosts with an ephemeral disk (Render free) files vanish on every deploy.
  s3    — any S3-compatible bucket: AWS S3, Cloudflare R2, Backblaze B2, MinIO.
          Durable, backed up by the provider, and shared by every server instance.

Pick one with STORAGE_BACKEND. Keys are validated so a key can never climb out of the
storage root / prefix.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9 ._()&+-]+")


def safe_segment(value: str | None, fallback: str = "Unknown") -> str:
    """One folder/file name component: no separators, dots-only or traversal."""
    cleaned = re.sub(r"\.{2,}", "_", _SAFE.sub("_", (value or "").strip())).strip(" .")   # no "..", ever
    return cleaned[:80] or fallback


def _check_key(key: str) -> str:
    parts = key.replace("\\", "/").split("/")
    if not key or key.startswith(("/", "\\")) or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid storage key.")
    return "/".join(parts)


class _Backend(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def healthcheck(self) -> None: ...


# --------------------------------------------------------------------------
# local disk
# --------------------------------------------------------------------------

class LocalBackend:
    def _root(self) -> Path:
        root = Path(settings.UPLOAD_DIR).expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        return root.resolve()

    def _path(self, key: str) -> Path:
        root = self._root()
        p = (root / _check_key(key)).resolve()
        if root != p and root not in p.parents:
            raise ValueError("Invalid storage key.")
        return p

    def save(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomic on the same volume

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    def healthcheck(self) -> None:
        root = self._root()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".health-{uuid.uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()


# --------------------------------------------------------------------------
# S3-compatible object storage
# --------------------------------------------------------------------------

class S3Backend:
    def __init__(self) -> None:
        self._client = None

    def _c(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            if not settings.S3_BUCKET:
                raise RuntimeError("STORAGE_BACKEND=s3 needs S3_BUCKET.")
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                region_name=settings.S3_REGION or None,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
                config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"},
                              connect_timeout=5, read_timeout=30),
            )
        return self._client

    @staticmethod
    def _k(key: str) -> str:
        return settings.S3_PREFIX.lstrip("/") + _check_key(key)

    def save(self, key: str, data: bytes) -> None:
        self._c().put_object(Bucket=settings.S3_BUCKET, Key=self._k(key), Body=data)

    def read(self, key: str) -> bytes:
        return self._c().get_object(Bucket=settings.S3_BUCKET, Key=self._k(key))["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._c().head_object(Bucket=settings.S3_BUCKET, Key=self._k(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        try:
            self._c().delete_object(Bucket=settings.S3_BUCKET, Key=self._k(key))
        except Exception:  # noqa: BLE001 — deleting a missing file is not an error
            pass

    def healthcheck(self) -> None:
        self._c().head_bucket(Bucket=settings.S3_BUCKET)


# --------------------------------------------------------------------------
# selection + public API
# --------------------------------------------------------------------------

_backend: _Backend | None = None
_backend_name: str | None = None


def backend() -> _Backend:
    global _backend, _backend_name
    name = settings.STORAGE_BACKEND.strip().lower()
    if _backend is None or _backend_name != name:
        if name == "s3":
            _backend = S3Backend()
        elif name == "local":
            _backend = LocalBackend()
        else:
            raise RuntimeError(f"Unknown STORAGE_BACKEND '{settings.STORAGE_BACKEND}' (use 'local' or 's3').")
        _backend_name = name
    return _backend


def reset_backend() -> None:
    """Forget the cached backend (tests change settings between runs)."""
    global _backend, _backend_name
    _backend, _backend_name = None, None


def save(key: str, data: bytes) -> None:
    backend().save(key, data)


def read(key: str) -> bytes:
    return backend().read(key)


def exists(key: str) -> bool:
    return backend().exists(key)


def delete(key: str) -> None:
    backend().delete(key)


def healthcheck() -> None:
    backend().healthcheck()
