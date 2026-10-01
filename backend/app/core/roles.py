"""
How staff are grouped everywhere (Team page, attendance): Admins, Accounts, and field
employees split by the platform they serve. Pure functions — no database access.
"""

ADMIN = "admin"
ACCOUNTANT = "accountant"

CATEGORY_LABELS = {
    "admin": "Admins",
    "accounts": "Accounts",
    "blinkit": "Blinkit employees",
    "zepto": "Zepto employees",
    "other": "Other employees",
}
# Display order.
CATEGORY_ORDER = ["admin", "accounts", "blinkit", "zepto", "other"]


def staff_category(roles: list[str] | set[str], platform_slug: str | None) -> str:
    """admin > accounts > the platform's employees. Admins who are also accountants count as admins."""
    if ADMIN in roles:
        return "admin"
    if ACCOUNTANT in roles:
        return "accounts"
    slug = (platform_slug or "").strip().lower()
    return slug if slug in ("blinkit", "zepto") else "other"
