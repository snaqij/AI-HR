"""候选人外部身份映射模型。"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class CandidateIdentity(TimestampMixin, Base):
    """候选人与渠道外部 ID 的映射关系。"""

    __tablename__ = "candidate_identities"
    __table_args__ = (UniqueConstraint("source_channel", "external_candidate_id", name="uq_identity_source_external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False)
    external_candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)

    candidate = relationship("Candidate", back_populates="identities")
