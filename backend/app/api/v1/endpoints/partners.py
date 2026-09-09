"""Partner organizations — read-only list for store forms / filters."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
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
    dependencies=[Depends(require_permission("stores.view"))],
)
def list_partners(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Organization]:
    stmt = (
        select(Organization)
        .where(Organization.kind == OrganizationKind.PARTNER.value, Organization.is_active.is_(True))
        .order_by(Organization.name)
    )
    return list(db.execute(stmt).scalars().all())
