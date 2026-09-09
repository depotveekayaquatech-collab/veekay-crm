"""Activity feed contract — a read-only view over audit_logs."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class ActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    actor_name: str | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
