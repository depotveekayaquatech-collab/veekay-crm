"""Pydantic request/response contracts for the auth endpoints."""
import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(default="veekay", description="Tenant slug")
    employee_code: str = Field(..., description="Employee ID, e.g. ADMIN001")
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    employee_code: str
    full_name: str
    email: str | None = None
    organization_id: uuid.UUID
    organization_slug: str
    platform_slug: str | None = None
    platform_label: str | None = None
    region_id: uuid.UUID | None = None
    region_name: str | None = None
    permissions: list[str]
    roles: list[str]
    is_admin: bool = False

    model_config = {"from_attributes": True}
