"""Pydantic request/response contracts for the auth endpoints."""
import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    organization_slug: str = Field(..., description="e.g. 'veekay', 'blinkit', 'zepto'")
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    organization_id: uuid.UUID
    organization_slug: str
    permissions: list[str]
    roles: list[str]

    model_config = {"from_attributes": True}
