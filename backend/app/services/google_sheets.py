"""
Private Google Sheet access with a service account (no extra dependency: PyJWT + cryptography are already installed).

The service-account key JSON lives only in the GOOGLE_SERVICE_ACCOUNT_JSON secret; it is never logged or returned.
The sheet is shared with the service account's e-mail address (Viewer). We sign a short-lived JWT, swap it for an access
token, and then download the tab with the same CSV export URL the public path uses, so the import code is unchanged.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt

from app.core.config import settings

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_lock = threading.Lock()
_cached: tuple[str, float] | None = None   # (access token, expires at)


class SheetsAccessError(Exception):
    """A readable reason the private sheet could not be fetched."""


def configured() -> bool:
    return bool(settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip())


def _credentials() -> dict:
    try:
        info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
        for k in ("client_email", "private_key"):
            if not info.get(k):
                raise KeyError(k)
        return info
    except (ValueError, KeyError):
        raise SheetsAccessError("GOOGLE_SERVICE_ACCOUNT_JSON is set but is not a valid service-account key.") from None


def service_account_email() -> str | None:
    """The address to share the sheets with (safe to show to developers)."""
    try:
        return _credentials()["client_email"] if configured() else None
    except SheetsAccessError:
        return None


def _access_token() -> str:
    global _cached
    with _lock:
        if _cached and _cached[1] - 60 > time.time():
            return _cached[0]
        info = _credentials()
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": info["client_email"], "scope": _SCOPE, "aud": _TOKEN_URL, "iat": now, "exp": now + 3000},
            info["private_key"], algorithm="RS256",
        )
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}).encode()
        req = urllib.request.Request(_TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed Google host
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise SheetsAccessError(f"Google refused the service-account key (HTTP {exc.code}). Check the key is current.") from None
        except urllib.error.URLError as exc:
            raise SheetsAccessError(f"Could not reach Google to sign in: {exc.reason}") from None
        _cached = (data["access_token"], time.time() + int(data.get("expires_in", 3000)))
        return _cached[0]


def fetch_csv(url: str) -> str:
    """Download a sheet export URL as the service account."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_access_token()}", "User-Agent": "veekay-crm-sheets/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed docs.google.com host
            return resp.read().decode("utf-8-sig", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            who = service_account_email() or "the service account"
            raise SheetsAccessError(f"The sheet is not shared with {who}. Share it with that address as Viewer.") from None
        raise SheetsAccessError(f"Google Sheets returned HTTP {exc.code} for this sheet.") from None
    except urllib.error.URLError as exc:
        raise SheetsAccessError(f"Could not reach Google Sheets: {exc.reason}") from None
