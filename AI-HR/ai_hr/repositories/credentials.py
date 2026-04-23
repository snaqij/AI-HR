"""Repository for managing channel credentials."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db.models.credential import ChannelCredential


class ChannelCredentialRepository:
    """Repository for ChannelCredential entity."""

    def __init__(self, session: Session):
        self._session = session

    def get_active_by_channel(self, channel: str, *, owner_user_id: str) -> ChannelCredential | None:
        """Fetch the active credential for a specific channel under one platform user."""
        stmt = (
            select(ChannelCredential)
            .where(ChannelCredential.channel == channel)
            .where(ChannelCredential.owner_user_id == owner_user_id)
            .where(ChannelCredential.is_active.is_(True))
            .order_by(ChannelCredential.updated_at.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def update_credential(
        self,
        channel: str,
        encrypted_config: str,
        *,
        owner_user_id: str,
        account_name: str = "Default Account",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelCredential:
        """Create or update a channel credential."""
        # Deactivate existing active credentials for this channel under the same user only.
        self._session.execute(
            update(ChannelCredential)
            .where(ChannelCredential.channel == channel)
            .where(ChannelCredential.owner_user_id == owner_user_id)
            .values(is_active=False)
        )
        
        # Check if we have an existing record for this user/account to reuse or create new.
        existing = (
            select(ChannelCredential)
            .where(ChannelCredential.channel == channel)
            .where(ChannelCredential.owner_user_id == owner_user_id)
            .where(ChannelCredential.account_name == account_name)
            .limit(1)
        )
        entity = self._session.execute(existing).scalar_one_or_none()
        
        if entity:
            entity.encrypted_config = encrypted_config
            entity.is_active = True
            entity.status = "normal"
            entity.failure_count = 0  # Reset on manual update
            entity.last_failure_at = None
            entity.metadata_json = metadata
            entity.updated_at = datetime.now(UTC).replace(tzinfo=None)
        else:
            entity = ChannelCredential(
                channel=channel,
                owner_user_id=owner_user_id,
                account_name=account_name,
                encrypted_config=encrypted_config,
                is_active=True,
                status="normal",
                failure_count=0,
                last_failure_at=None,
                metadata_json=metadata
            )
            self._session.add(entity)
            
        return entity

    def mark_expired(self, credential_id: str, error_message: str | None = None) -> None:
        """Mark a credential as expired."""
        stmt = (
            update(ChannelCredential)
            .where(ChannelCredential.id == credential_id)
            .values(
                status="expired",
                last_failure_at=datetime.now(UTC).replace(tzinfo=None),
                failure_count=ChannelCredential.failure_count + 1
            )
        )
        self._session.execute(stmt)
