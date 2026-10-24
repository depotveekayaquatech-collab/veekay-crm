"""Request bodies for the entry audit / correction / review / role endpoints. The creator, role, scope and timestamps are never accepted from a client."""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")      # a request that tries to send creator_id, role, owner... is refused, not silently ignored


class EntryEdit(_Strict):
    bottle_count: int = Field(..., ge=0, le=200)
    reason: str = Field(..., min_length=1, max_length=500)
    expected_version: int = Field(..., ge=1)


class EntryReview(_Strict):
    action: Literal["reviewed", "flagged", "needs_correction", "clear"]
    comment: str | None = Field(default=None, max_length=1000)


class EntryVerify(_Strict):
    comment: str | None = Field(default=None, max_length=1000)


class EntryCheckRequest(_Strict):
    note: str | None = Field(default=None, max_length=1000)


class EntryComment(_Strict):
    text: str = Field(..., min_length=1, max_length=1000)


class EntryRoleSet(_Strict):
    level: Literal["entry_contributor", "team_lead", "entry_reviewer"] | None = None
    reports_to_id: uuid.UUID | None = None         # send null to clear; omit to leave unchanged
