"""Permission catalogue — for the admin 'what can this employee see' UI."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.permission import Permission

router = APIRouter(prefix="/permissions", tags=["permissions"])

_GROUP_LABELS = {
    "orders": "Orders",
    "stores": "Stores",
    "regions": "Regions",
    "employees": "Employees",
    "assignments": "Assignments",
    "activity": "Activity",
    "reports": "Reports",
}


class PermissionItem(BaseModel):
    code: str
    description: str


class PermissionGroup(BaseModel):
    key: str
    label: str
    permissions: list[PermissionItem]


@router.get(
    "", response_model=list[PermissionGroup],
    dependencies=[Depends(require_permission("employees.create"))],
)
def list_permissions(db: Session = Depends(get_db)) -> list[PermissionGroup]:
    rows = db.execute(select(Permission).order_by(Permission.code)).scalars().all()
    groups: dict[str, list[PermissionItem]] = {}
    for p in rows:
        key = p.code.split(".")[0]
        groups.setdefault(key, []).append(PermissionItem(code=p.code, description=p.description))
    return [
        PermissionGroup(key=k, label=_GROUP_LABELS.get(k, k.title()), permissions=v)
        for k, v in sorted(groups.items())
    ]
