import uuid
from datetime import datetime

from pydantic import BaseModel


class ExternalAccountOut(BaseModel):
    id: uuid.UUID
    kind: str                       # vendor | poc
    email: str
    full_name: str
    phone: str | None
    platforms: list[str]
    store_count: int
    must_change_password: bool
    is_active: bool
    created_at: datetime


class ExternalAccountList(BaseModel):
    items: list[ExternalAccountOut]
    total: int
    page: int
    page_size: int
    vendors: int
    pocs: int


class StoreRef(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    platform: str | None = None
    city: str | None = None
    state: str | None = None


class ExternalAccountDetail(BaseModel):
    account: ExternalAccountOut
    stores: list[StoreRef]
