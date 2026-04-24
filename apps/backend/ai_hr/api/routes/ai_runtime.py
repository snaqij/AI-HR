"""AI runtime management routes."""

from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...core.responses import Envelope
from ...db.session import get_db_session
from ...schemas.ai_runtime import (
    RuntimeFeatureFlagRequest,
    RuntimeFeatureFlagResponse,
    RuntimeModelConfigRequest,
    RuntimeModelConfigResponse,
    RuntimePromptRequest,
    RuntimePromptResponse,
)
from ...services.ai_runtime import get_ai_runtime_service

router = APIRouter(prefix="/ai/runtime", tags=["ai-runtime"])


@router.put("/feature-flags/{feature_key}", response_model=Envelope[RuntimeFeatureFlagResponse])
def upsert_feature_flag(
    feature_key: str,
    payload: RuntimeFeatureFlagRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimeFeatureFlagResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.upsert_feature_flag(feature_key, payload))


@router.get("/feature-flags/{feature_key}", response_model=Envelope[RuntimeFeatureFlagResponse | None])
def get_feature_flag(
    feature_key: str,
    tenant_id: str | None = None,
    job_id: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimeFeatureFlagResponse | None]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.get_feature_flag(feature_key, tenant_id=tenant_id, job_id=job_id))


@router.post("/feature-flags/{feature_key}/rollback", response_model=Envelope[RuntimeFeatureFlagResponse])
def rollback_feature_flag(
    feature_key: str,
    tenant_id: str | None = None,
    job_id: str | None = None,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimeFeatureFlagResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.rollback_feature_flag(feature_key, tenant_id=tenant_id, job_id=job_id))


@router.put("/model-configs/{task_key}", response_model=Envelope[RuntimeModelConfigResponse])
def upsert_model_config(
    task_key: str,
    payload: RuntimeModelConfigRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimeModelConfigResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.upsert_model_config(task_key, payload))


@router.get("/model-configs/{task_key}", response_model=Envelope[RuntimeModelConfigResponse | None])
def get_model_config(
    task_key: str,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimeModelConfigResponse | None]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.get_active_model_config(task_key))


@router.put("/prompts/{task_key}", response_model=Envelope[RuntimePromptResponse])
def upsert_prompt(
    task_key: str,
    payload: RuntimePromptRequest,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimePromptResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.upsert_prompt(task_key, payload))


@router.get("/prompts/{task_key}", response_model=Envelope[RuntimePromptResponse | None])
def get_prompt(
    task_key: str,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimePromptResponse | None]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.get_active_prompt(task_key))


@router.get("/prompts/{task_key}/versions", response_model=Envelope[list[RuntimePromptResponse]])
def list_prompt_versions(
    task_key: str,
    session: Session = Depends(get_db_session),
) -> Envelope[list[RuntimePromptResponse]]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.list_prompt_versions(task_key))


@router.post("/prompts/{task_key}/versions/{version}/activate", response_model=Envelope[RuntimePromptResponse])
def activate_prompt_version(
    task_key: str,
    version: str,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimePromptResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.activate_prompt(task_key, version))


@router.post("/prompts/{task_key}/rollback", response_model=Envelope[RuntimePromptResponse])
def rollback_prompt_version(
    task_key: str,
    session: Session = Depends(get_db_session),
) -> Envelope[RuntimePromptResponse]:
    service = get_ai_runtime_service(session)
    return Envelope.success(service.rollback_prompt(task_key))
