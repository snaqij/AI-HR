"""Credential management API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.session import get_db_session
from ...schemas.credentials import CredentialResponse, CredentialUpdateRequest
from ...services.credentials import get_credential_service


router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("/{channel}", response_model=CredentialResponse)
def get_channel_credential(
    channel: str,
    session: Session = Depends(get_db_session),
) -> Any:
    """Get the active credential for a channel (redacted)."""
    service = get_credential_service(session)
    # We use the internal repo through the service for this simple GET
    credential = service._repository.get_active_by_channel(channel)
    if not credential:
        raise HTTPException(status_code=404, detail=f"No active credential found for channel '{channel}'")
    return credential


@router.post("/{channel}")
def update_channel_credential(
    channel: str,
    payload: CredentialUpdateRequest,
    session: Session = Depends(get_db_session),
) -> Any:
    """Update the credential (cookie) for a channel."""
    if channel != "boss":
        raise HTTPException(status_code=400, detail="Only 'boss' channel is supported currently")
        
    service = get_credential_service(session)
    success = service.update_boss_cookie(
        cookie_header=payload.cookie_header,
        account_name=payload.account_name
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update credential")
        
    return {"status": "success", "message": f"Credential for '{channel}' updated successfully"}
