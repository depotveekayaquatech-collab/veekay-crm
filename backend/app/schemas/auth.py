"""Pydantic request/response contracts for the auth endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(default="veekay", description="Tenant slug")
    employee_code: str = Field(..., description="Employee ID, e.g. ADMIN001")
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenPair):
    # Always False now: attendance is an explicit Check in (see /attendance/check-in), never a side effect of signing in.
    # Kept so older clients that read the field keep working.
    attendance: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


class SessionOut(BaseModel):
    id: uuid.UUID            # the session family id
    current: bool
    signed_in_at: datetime
    last_active_at: datetime
    ip: str | None = None
    user_agent: str | None = None


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
    must_change_password: bool = False

    model_config = {"from_attributes": True}
