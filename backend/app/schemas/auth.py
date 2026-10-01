"""Pydantic request/response contracts for the auth endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(default="veekay", description="Tenant slug")
    employee_code: str = Field(..., description="Employee ID, e.g. ADMIN001")
    password: str
    # Optional: where the device is at sign-in, for attendance. Signing in never depends on it.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100000, description="metres")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(TokenPair):
    # True when this sign-in counts as attendance (employees / accounts, never admins): the app then reads the
    # device location once, right after login, and posts it to /attendance/location.
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
