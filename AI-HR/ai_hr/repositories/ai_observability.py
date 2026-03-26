"""AI 可观测与审计仓储。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import AIDecisionLog, AIRequestTrace


class AIObservabilityRepository:
    """封装 AI trace 与决策日志读写。"""

    def __init__(self, session: Session):
        """使用数据库会话初始化仓储。"""
        self._session = session

    def create_trace(
        self,
        *,
        trace_id: str,
        task_key: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        request_hash: str,
        response_status: str,
        latency_ms: int,
        retry_count: int,
        fallback_used: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> AIRequestTrace:
        """创建 AI 请求追踪记录。"""
        entity = AIRequestTrace(
            trace_id=trace_id,
            task_key=task_key,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
            request_hash=request_hash,
            response_status=response_status,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            retry_count=retry_count,
            fallback_used=1 if fallback_used else 0,
            finished_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def create_decision_log(
        self,
        *,
        trace_id: str,
        module_key: str,
        entity_type: str,
        entity_id: str,
        action: str,
        confidence: float | None = None,
        risk_tags: list[str] | None = None,
        policy_flags: list[str] | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        provider: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        extra_payload: dict | None = None,
    ) -> AIDecisionLog:
        """创建 AI 决策日志。"""
        entity = AIDecisionLog(
            trace_id=trace_id,
            module_key=module_key,
            entity_type=entity_type,
            entity_id=entity_id,
            confidence=confidence,
            risk_tags=risk_tags or [],
            policy_flags=policy_flags or [],
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
            extra_payload=extra_payload or {},
        )
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_reply_alert_stats(
        self,
        *,
        window_minutes: int,
        handoff_alert_threshold: float,
        blocked_alert_threshold: float,
        min_samples: int,
    ) -> dict[str, int | float | bool | list[str]]:
        """统计自动回复策略告警指标。"""
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=window_minutes)
        base_query = select(AIDecisionLog).where(
            AIDecisionLog.module_key == "reply_policy",
            AIDecisionLog.created_at >= since,
        )

        total_stmt = select(func.count()).select_from(base_query.subquery())
        total = int(self._session.execute(total_stmt).scalar_one() or 0)

        handoff_stmt = select(func.count(AIDecisionLog.id)).where(
            AIDecisionLog.module_key == "reply_policy",
            AIDecisionLog.created_at >= since,
            AIDecisionLog.action == "handoff",
        )
        handoff_count = int(self._session.execute(handoff_stmt).scalar_one() or 0)

        blocked_stmt = select(func.count(AIDecisionLog.id)).where(
            AIDecisionLog.module_key == "reply_policy",
            AIDecisionLog.created_at >= since,
            AIDecisionLog.action == "blocked",
        )
        blocked_count = int(self._session.execute(blocked_stmt).scalar_one() or 0)

        handoff_rate = round((handoff_count / total), 4) if total > 0 else 0.0
        blocked_rate = round((blocked_count / total), 4) if total > 0 else 0.0

        alert_reasons: list[str] = []
        if total >= min_samples and handoff_rate >= handoff_alert_threshold:
            alert_reasons.append("handoff_rate_high")
        if total >= min_samples and blocked_rate >= blocked_alert_threshold:
            alert_reasons.append("blocked_rate_high")

        return {
            "window_minutes": window_minutes,
            "total": total,
            "handoff_count": handoff_count,
            "blocked_count": blocked_count,
            "handoff_rate": handoff_rate,
            "blocked_rate": blocked_rate,
            "min_samples": min_samples,
            "alerting": bool(alert_reasons),
            "alert_reasons": alert_reasons,
        }
