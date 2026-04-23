"""Decision policy version persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class DecisionPolicyVersion(TimestampMixin, Base):
    """Stores versioned policy configs for progression decisions."""

    __tablename__ = "decision_policy_versions"
    __table_args__ = (
        Index("uk_decision_policy_code_version", "policy_code", "version", unique=True),
        Index("idx_decision_policy_status_window", "status", "effective_from", "effective_to"),
        Index("idx_decision_policy_default", "is_default"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resume_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.35)
    interview_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.45)
    market_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.15)
    stability_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.05)
    risk_penalty_weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.2)
    hard_rules_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    threshold_rules_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    override_rules_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    formula_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
