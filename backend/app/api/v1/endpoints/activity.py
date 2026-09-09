"""Activity feed route — read-only view over audit_logs."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.activity import ActivityOut
from app.schemas.common import Page, PageParams
from app.services import activity_service

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get(
    "", response_model=Page[ActivityOut],
    dependencies=[Depends(require_permission("activity.view"))],
)
def list_activity(
    entity_type: str | None = None,
    params: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ActivityOut]:
    return activity_service.list_activity(db, user.organization_id, params, entity_type=entity_type)
