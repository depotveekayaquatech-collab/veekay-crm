"""
How staff are grouped everywhere (Team page, attendance): Admins, Accounts, and field
employees split by the platform they serve. Pure functions — no database access.
"""

ADMIN = "admin"
ACCOUNTANT = "accountant"
MANAGER = "manager"  # a "custom admin": counts as an admin on the Team page, but only holds the permissions ticked for them
DEVELOPER = "developer" 
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

# Permissions that only the developer role can hold (the developer holds every permission, these included). Admins never get them (not even a "full" admin), they can't be
# granted per person, and the permission catalogue doesn't list them.
RESERVED_PERMISSIONS = frozenset({"sheets.sync", "cash.adjust", "bottles.delete", "cards.sheet", "attendance.edit", "employees.delete", "employees.view_password"})

# Two of the reserved permissions are also given to Level 3 (the Entry Reviewer role, whatever platform it serves) and Level 4 (administrators), computed
# per request in UserRepository.get_permission_codes: the cash-purchase tools (sheet import + manual add) and the random card PDF (still behind its access code).
# They stay reserved: nobody can be granted them per person or through a custom role, and Level 1 / Level 2 never hold them, so those routes answer 403.
LEVEL3_TOOL_PERMISSIONS = frozenset({"cash.adjust", "cards.sheet"})

# Accounts (the accountant role) also get the random card PDF (still behind its access code), but not the cash-purchase tools.
ACCOUNTS_TOOL_PERMISSIONS = frozenset({"cards.sheet"})

# The only permissions a partner account may ever hold — enforced server-side whatever the UI sends.
PARTNER_PERMISSIONS = ["orders.view", "tickets.view", "tickets.create", "reports.delivery"]


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
