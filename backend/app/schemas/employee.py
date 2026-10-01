"""Employee (= User with the 'employee' role) request/response contracts."""
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class EmployeeCreate(BaseModel):
    employee_code: str = Field(..., min_length=1, max_length=32)
    full_name: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    platform_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None
    permission_codes: list[str] = Field(default_factory=list)
    # "partner" = a Blinkit / Zepto login: needs a platform, never a region, and only partner-safe permissions.
    account_type: Literal["employee", "partner", "admin"] = "employee"
    # For account_type "admin": "full" = every permission (the Admin role); "custom" = only permission_codes.
    admin_access: Literal["full", "custom"] = "full"


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class EmployeeScope(BaseModel):
    platform_id: uuid.UUID | None = None
    region_id: uuid.UUID | None = None


class AdminAccess(BaseModel):
    full: bool


class PermissionSet(BaseModel):
    codes: list[str]


class EmployeeOut(BaseModel):
    id: uuid.UUID
    employee_code: str
    full_name: str
    email: EmailStr | None
    phone: str | None
    status: str
    is_active: bool
    platform_id: uuid.UUID | None
    platform_slug: str | None = None
    region_id: uuid.UUID | None
    region_name: str | None = None
    states: list[str] = []
    roles: list[str] = []
    category: str = "other"        # admin | accounts | blinkit | zepto | other
    category_label: str = ""
    admin_level: Literal["full", "custom"] | None = None   # set for admin-category accounts
    direct_permissions: list[str] = []

    model_config = {"from_attributes": True}


class ImportedCredential(BaseModel):
    employee_code: str
    full_name: str
    temp_password: str


class EmployeeImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    skipped: int
    assignments: int
    credentials: list[ImportedCredential]
    warnings: list[str]
