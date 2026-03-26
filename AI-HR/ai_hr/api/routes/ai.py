"""AI 模块路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_scoring import (
    AICandidateBatchScoreRequest,
    AICandidateBatchScoreResult,
    AICandidateRankRequest,
    AICandidateRankResult,
)
from ...schemas.ai_reply import (
    AIIntentClassifyRequest,
    AIIntentClassifyResult,
    AIReplyGenerateRequest,
    AIReplyGenerateResult,
)
from ...schemas.ai_eval import AIEvalReportResult, AIEvalRunRequest, AIEvalRunResult
from ...schemas.ai_resume import ResumeNormalizeRequest, ResumeNormalizeResult, ResumeParseRequest, ResumeParseResult
from ...services.ai_eval import get_ai_eval_service
from ...services.ai_scoring import get_ai_scoring_service
from ...services.ai_reply_llm import get_ai_reply_llm_service
from ...services.ai_resume import get_ai_resume_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/resume/parse", response_model=Envelope[ResumeParseResult])
def parse_resume(
    payload: ResumeParseRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeParseResult]:
    """执行简历解析并写入结构化画像。"""
    service = get_ai_resume_service(session)
    result = service.parse_resume(payload)
    return Envelope.success(result)


@router.post("/resume/normalize", response_model=Envelope[ResumeNormalizeResult])
def normalize_resume(
    payload: ResumeNormalizeRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[ResumeNormalizeResult]:
    """执行简历字段标准化并刷新风险标签。"""
    service = get_ai_resume_service(session)
    result = service.normalize_resume(payload)
    return Envelope.success(result)


@router.post("/candidates/score", response_model=Envelope[AICandidateBatchScoreResult])
def batch_score_candidates(
    payload: AICandidateBatchScoreRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AICandidateBatchScoreResult]:
    """按岗位批量执行候选人评分。"""
    service = get_ai_scoring_service(session)
    result = service.batch_score(payload)
    return Envelope.success(result)


@router.post("/candidates/rank", response_model=Envelope[AICandidateRankResult])
def rank_candidates(
    payload: AICandidateRankRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AICandidateRankResult]:
    """按岗位评分结果生成排序与入围名单。"""
    service = get_ai_scoring_service(session)
    result = service.rank_candidates(payload)
    return Envelope.success(result)


@router.post("/reply/classify-intent", response_model=Envelope[AIIntentClassifyResult])
def classify_intent(
    payload: AIIntentClassifyRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIIntentClassifyResult]:
    """独立执行会话意图分类。"""
    service = get_ai_reply_llm_service(session)
    result = service.classify_intent(conversation_id=payload.conversation_id, message=payload.message)
    return Envelope.success(result)


@router.post("/reply/generate", response_model=Envelope[AIReplyGenerateResult])
def generate_reply(
    payload: AIReplyGenerateRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIReplyGenerateResult]:
    """独立生成自动回复。"""
    service = get_ai_reply_llm_service(session)
    result = service.generate_reply_result(
        conversation_id=payload.conversation_id,
        message=payload.message,
        intent_hint=payload.intent_hint,
    )
    return Envelope.success(result)


@router.post("/eval/run", response_model=Envelope[AIEvalRunResult])
def run_ai_eval(
    payload: AIEvalRunRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[AIEvalRunResult]:
    """创建一次 AI 离线评测运行记录。"""
    service = get_ai_eval_service(session)
    result = service.run_eval(payload)
    return Envelope.success(result)


@router.get("/eval/report", response_model=Envelope[AIEvalReportResult])
def get_ai_eval_report(
    eval_type: str,
    run_id: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[AIEvalReportResult]:
    """按评测类型查询最新报告，或按 run_id 精确查询。"""
    service = get_ai_eval_service(session)
    result = service.get_report(eval_type=eval_type, run_id=run_id)
    return Envelope.success(result)
