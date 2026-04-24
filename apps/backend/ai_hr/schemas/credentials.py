"""Credential management schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CredentialUpdateRequest(BaseModel):
    """Request schema for updating a channel credential."""
    cookie_header: str = Field(..., description="The full Cookie header string from the browser.")
    account_name: str = Field("Primary Account", description="An optional nickname for this account.")


class CredentialResponse(BaseModel):
    """Response schema for credential information (redacted)."""
    id: str
    channel: str
    account_name: str
    status: str
    is_active: bool
    last_validated_at: datetime | None = None
    last_failure_at: datetime | None = None
    failure_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)
