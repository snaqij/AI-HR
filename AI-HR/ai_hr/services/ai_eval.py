"""AI 离线评测服务。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..core.exceptions import ResourceNotFoundError
from ..repositories.ai_eval import AIEvalRepository
from ..schemas.ai_eval import AIEvalReportResult, AIEvalRunRequest, AIEvalRunResult


class AIEvalService:
    """提供离线评测运行与报告查询能力。"""

    def __init__(self, session: Session):
        self._repository = AIEvalRepository(session)

    def run_eval(self, payload: AIEvalRunRequest) -> AIEvalRunResult:
        """创建最小可执行评测运行记录并返回摘要。"""
        started_at = datetime.now(UTC)
        metrics = self._build_metrics(payload.eval_type)
        finished_at = datetime.now(UTC)
        entity = self._repository.create_run(
            eval_type=payload.eval_type,
            dataset_version=payload.dataset_version,
            model_version=payload.model_version,
            metrics=metrics,
            started_at=started_at,
            finished_at=finished_at,
        )
        return AIEvalRunResult(
            run_id=entity.id,
            eval_type=entity.eval_type,
            dataset_version=entity.dataset_version,
            model_version=entity.model_version,
            status=entity.status,
            metrics=entity.metrics,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
        )

    def get_report(self, *, eval_type: str, run_id: str | None = None) -> AIEvalReportResult:
        """查询指定运行或类型最新运行的指标报告。"""
        entity = self._repository.get_run(run_id) if run_id else self._repository.get_latest_run(eval_type)
        if entity is None:
            raise ResourceNotFoundError(f"AI eval report not found for eval_type='{eval_type}'")
        return AIEvalReportResult(
            run_id=entity.id,
            eval_type=entity.eval_type,
            dataset_version=entity.dataset_version,
            model_version=entity.model_version,
            status=entity.status,
            metrics=entity.metrics,
            finished_at=entity.finished_at,
        )

    def _build_metrics(self, eval_type: str) -> dict[str, float]:
        """构造最小可用指标，后续可替换为真实离线评测。"""
        default_metrics = {"sample_size": 100.0, "success_rate": 0.9}
        metric_map = {
            "resume_parse": {"sample_size": 120.0, "parse_success_rate": 0.93, "field_coverage_rate": 0.9},
            "reply_generate": {"sample_size": 90.0, "intent_accuracy": 0.86, "reply_accept_rate": 0.78},
        }
        return metric_map.get(eval_type, default_metrics)


def get_ai_eval_service(session: Session) -> AIEvalService:
    """返回绑定当前数据库会话的 AIEvalService。"""
    return AIEvalService(session)
