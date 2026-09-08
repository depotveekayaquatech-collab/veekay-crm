"""
Run once against a fresh database to create enough data to log in:
one organization, two roles, a starter permission set, and one admin user.

    python scripts/seed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.organization import Organization, OrganizationKind
from app.models.permission import Permission, RolePermission
from app.models.role import Role
from app.models.user import User, UserRole, UserStatus

PERMISSIONS = [
    ("orders.view", "View orders"),
    ("orders.create", "Create orders"),
    ("orders.assign", "Assign orders"),
    ("orders.update", "Update order status"),
    ("orders.verify", "Verify orders"),
    ("tickets.view", "View tickets"),
    ("tickets.create", "Create tickets"),
    ("tickets.verify", "Verify tickets"),
    ("tickets.resolve", "Resolve tickets"),
    ("employees.view", "View employees"),
    ("employees.create", "Create employees"),
    ("employees.update", "Update employees"),
    ("reports.view", "View reports"),
    ("reports.export", "Export reports"),
]

ADMIN_PERMISSIONS = [code for code, _ in PERMISSIONS]
EMPLOYEE_PERMISSIONS = ["orders.view", "orders.update", "tickets.view", "tickets.create"]

# Starter password for both seeded users. Change these before this goes
# anywhere near production.
SEED_PASSWORD = "Pass@123"


def main() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug="veekay").first()
        if org is None:
            org = Organization(slug="veekay", name="Veekay Aquatech", kind=OrganizationKind.INTERNAL.value)
            db.add(org)
            db.flush()

        permissions_by_code = {}
        for code, description in PERMISSIONS:
            perm = db.query(Permission).filter_by(code=code).first()
            if perm is None:
                perm = Permission(code=code, description=description)
                db.add(perm)
                db.flush()
            permissions_by_code[code] = perm

        def ensure_role(code: str, name: str, permission_codes: list[str]) -> Role:
            role = db.query(Role).filter_by(code=code).first()
            if role is None:
                role = Role(code=code, name=name)
                db.add(role)
                db.flush()
            existing = {rp.permission_id for rp in role.role_permissions}
            for perm_code in permission_codes:
                perm = permissions_by_code[perm_code]
                if perm.id not in existing:
                    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
            return role

        admin_role = ensure_role("admin", "Admin", ADMIN_PERMISSIONS)
        employee_role = ensure_role("employee", "Employee", EMPLOYEE_PERMISSIONS)
        db.flush()

        def ensure_user(email: str, full_name: str, password: str, role: Role) -> None:
            user = db.query(User).filter_by(organization_id=org.id, email=email).first()
            if user is None:
                user = User(
                    organization_id=org.id,
                    full_name=full_name,
                    email=email,
                    password_hash=hash_password(password),
                    status=UserStatus.ACTIVE.value,
                )
                db.add(user)
                db.flush()
            if not db.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first():
                db.add(UserRole(user_id=user.id, role_id=role.id))

        ensure_user("admin@veekay.com", "Admin User", SEED_PASSWORD, admin_role)
        ensure_user("employee@veekay.com", "Employee User", SEED_PASSWORD, employee_role)

        db.commit()
        print("Seeded: organization 'veekay', roles admin/employee, 2 users.")
        print(f"  admin@veekay.com    / {SEED_PASSWORD}  (admin role)")
        print(f"  employee@veekay.com / {SEED_PASSWORD}  (employee role)")
        print("Login with organization='veekay'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
