"""
The one place that knows what a vendor code looks like and where it sits in a Busy account name.

Default: the code is the LAST whitespace-separated word of the account name and fully matches BUSY_VENDOR_CODE_REGEX (default `^V\\d{4}$`),
so "Sharma Traders Gurugram V0123" -> "V0123". Change the format by changing that one setting; nothing else needs to know.
Codes are compared upper-cased and trimmed everywhere, so "v0123 " and "V0123" are the same vendor.
"""
import re
from functools import lru_cache

from app.core.config import settings

MAX_CODE_LENGTH = 32
_VALID_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")


@lru_cache(maxsize=8)
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def normalize_code(raw: object) -> str:
    """Trim and upper-case a code (no other change). Empty string when there is nothing there."""
    return str(raw).strip().upper() if raw is not None else ""


def is_valid_code(code: str) -> bool:
    """A code an admin may give a vendor: letters, digits, `-` and `_`, up to 32 characters. (The extraction pattern is separate: it is only for finding a code in a name.)"""
    return bool(code) and len(code) <= MAX_CODE_LENGTH and bool(_VALID_CODE.match(code))


def extract_vendor_code(account_name: str | None, pattern: str | None = None) -> str | None:
    """The vendor code at the end of a Busy account name, or None when the last word is not a code."""
    words = (account_name or "").split()
    if not words:
        return None
    last = words[-1]
    if _compiled(pattern or settings.BUSY_VENDOR_CODE_REGEX).fullmatch(last):
        return normalize_code(last)
    return None


def split_account_name(account_name: str | None) -> tuple[str, str | None]:
    """("Sharma Traders Gurugram V0123") -> ("Sharma Traders Gurugram", "V0123"): the display name without its code, and the code."""
    code = extract_vendor_code(account_name)
    name = " ".join((account_name or "").split())
    if code and name.upper().endswith(code):
        name = name[: -len(code)].rstrip()
    return name, code
