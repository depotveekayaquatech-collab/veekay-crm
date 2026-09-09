"""Region request/response contracts."""
import uuid

from pydantic import BaseModel, Field


class RegionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=1, max_length=32)


class RegionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    code: str | None = Field(default=None, min_length=1, max_length=32)
    is_active: bool | None = None


class RegionOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    store_count: int = 0

    model_config = {"from_attributes": True}
