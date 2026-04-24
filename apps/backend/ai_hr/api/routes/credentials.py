"""Credential management API routes."""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...core.auth_dependencies import require_workspace_context
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.credentials import CredentialResponse, CredentialUpdateRequest
from ...services.credentials import get_credential_service


router = APIRouter(prefix="/credentials", tags=["credentials"], dependencies=[Depends(require_workspace_context)])


@router.get("/{channel}", response_model=Envelope[CredentialResponse])
def get_channel_credential(
    channel: str,
    session: Session = Depends(get_db_session),
) -> Envelope[CredentialResponse]:
    """Get the active credential for the current platform user (redacted)."""
    service = get_credential_service(session)
    credential = service.get_current_channel_credential(channel)
    if not credential:
        raise HTTPException(status_code=404, detail=f"No active credential found for current user on channel '{channel}'")
    return Envelope.success(CredentialResponse.model_validate(credential))


@router.post("/{channel}/validate", response_model=Envelope[CredentialResponse])
def validate_channel_credential(
    channel: str,
    session: Session = Depends(get_db_session),
) -> Envelope[CredentialResponse]:
    """Actively validate the credential against the upstream platform."""
    service = get_credential_service(session)
    credential = service.validate_current_channel_credential(channel)
    if not credential:
        raise HTTPException(status_code=404, detail=f"No active credential found for current user on channel '{channel}'")
    return Envelope.success(CredentialResponse.model_validate(credential))


@router.post("/{channel}", response_model=Envelope[dict[str, str]])
def update_channel_credential(
    channel: str,
    payload: CredentialUpdateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[dict[str, str]]:
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

    return Envelope.success(
        {"status": "success", "message": f"Credential for '{channel}' updated successfully"}
    )
