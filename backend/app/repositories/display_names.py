"""The name shown for a user inside SQL queries (see User.display_name for the same rule on a loaded user)."""
from sqlalchemy import case, literal, select

from app.core.roles import DEVELOPER
from app.models.role import Role
from app.models.user import User, UserRole

SHOWN_AS = "Admin"


def shown_name():
    """`User.full_name`, except the developer, who appears as "Admin"."""
    developers = select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == DEVELOPER)
    return case((User.id.in_(developers), literal(SHOWN_AS)), else_=User.full_name)
