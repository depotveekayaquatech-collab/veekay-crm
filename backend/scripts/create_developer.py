"""
Create (or promote) a developer account. This is the ONLY way to get one: the app never offers the developer
role, and no admin screen or API can grant it.

    python scripts/create_developer.py DEV001 "Full Name"          # prompts for the password
    python scripts/create_developer.py DEV001 "Full Name" --password '...'
    python scripts/create_developer.py EXISTING001 --promote        # add the role to an existing account

A developer holds ONLY 'sheets.sync' (store sheet sync / file upload, order sheet sync / upload) and sees only the
Data sync page: none of an admin's rights. The account is hidden from the Users & access page, so admins cannot edit, reset or deactivate it.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.roles import DEVELOPER  # noqa: E402
from app.core.security import hash_password, validate_password_strength  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User, UserRole, UserStatus  # noqa: E402


def make_developer(db, code: str, name: str | None, password: str | None, promote: bool = False) -> User:
    org = db.query(Organization).filter_by(slug="veekay").one()
    role = db.query(Role).filter_by(code=DEVELOPER).first()
    if role is None:
        raise SystemExit("The developer role doesn't exist yet. Run: alembic upgrade head")
    user = db.query(User).filter_by(organization_id=org.id, employee_code=code).first()
    if promote:
        if user is None:
            raise SystemExit(f"No account '{code}' to promote.")
    elif user is not None:
        raise SystemExit(f"'{code}' already exists. Use --promote to add the developer role to it.")
    else:
        if not name or not password:
            raise SystemExit("A name and password are required for a new account.")
        problem = validate_password_strength(password)
        if problem:
            raise SystemExit(problem)
        user = User(
            organization_id=org.id, employee_code=code, full_name=name, password_hash=hash_password(password),
            status=UserStatus.ACTIVE.value, must_change_password=False,
        )
        db.add(user)
        db.flush()
    if not db.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first():
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--password")
    ap.add_argument("--promote", action="store_true")
    a = ap.parse_args()
    password = a.password
    if not a.promote and not password:
        password = getpass.getpass("Password: ")
    db = SessionLocal()
    try:
        u = make_developer(db, a.code.strip(), a.name, password, a.promote)
        print(f"Developer account ready: {u.employee_code} ({u.full_name}). Sign in with organization='veekay'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
