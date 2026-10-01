"""
How staff are grouped everywhere (Team page, attendance): Admins, Accounts, and field
employees split by the platform they serve. Pure functions — no database access.
"""

ADMIN = "admin"
ACCOUNTANT = "accountant"
MANAGER = "manager"  # a "custom admin": counts as an admin on the Team page, but only holds the permissions ticked for them
PARTNER = "partner"  # a Blinkit / Zepto login: sees only its own platform, and only what an admin switched on

CATEGORY_LABELS = {
    "admin": "Admins",
    "accounts": "Accounts",
    "partner": "Partner accounts",
    "blinkit": "Blinkit employees",
    "zepto": "Zepto employees",
    "other": "Other employees",
}
# Display order.
CATEGORY_ORDER = ["admin", "accounts", "partner", "blinkit", "zepto", "other"]

# The only permissions a partner account may ever hold — enforced server-side whatever the UI sends.
PARTNER_PERMISSIONS = ["orders.view", "tickets.view", "tickets.create"]


def staff_category(roles: list[str] | set[str], platform_slug: str | None) -> str:
    """admin > accounts > the platform's employees. Admins who are also accountants count as admins."""
    if ADMIN in roles or MANAGER in roles:
        return "admin"
    if ACCOUNTANT in roles:
        return "accounts"
    if PARTNER in roles:
        return "partner"
    slug = (platform_slug or "").strip().lower()
    return slug if slug in ("blinkit", "zepto") else "other"
