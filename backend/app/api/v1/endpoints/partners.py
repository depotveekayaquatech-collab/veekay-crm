"""Partner organizations — read-only list for store forms / filters."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.organization import Organization, OrganizationKind
from app.models.user import User

router = APIRouter(prefix="/partners", tags=["partners"])


class PartnerOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str

    model_config = {"from_attributes": True}


@router.get(
    "", response_model=list[PartnerOut],
)
def list_partners(
    user: User = Depends(get_current_user),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> list[Organization]:
    # Just the platform names: the Data sync page (developer) needs them to pick a platform.
    if not ({"stores.view", "sheets.sync"} & perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to access this.")
    stmt = (
        select(Organization)
        .where(Organization.kind == OrganizationKind.PARTNER.value, Organization.is_active.is_(True))
        .order_by(Organization.name)
    )
    return list(db.execute(stmt).scalars().all())
