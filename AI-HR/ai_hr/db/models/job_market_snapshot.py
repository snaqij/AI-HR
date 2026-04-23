"""Job market snapshot persistence model."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class JobMarketSnapshot(TimestampMixin, Base):
    """Stores market-context signals for a job at a point in time."""

    __tablename__ = "job_market_snapshots"
    __table_args__ = (
        Index("uk_job_market_snapshot", "job_id", "market_scope", "snapshot_date", unique=True),
        Index("idx_job_market_snapshot_date", "snapshot_date"),
        Index("idx_job_market_score", "market_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    market_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="cn")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    supply_index: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    demand_index: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    salary_p50: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_p75: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    competition_index: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    market_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=50)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="internal")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
