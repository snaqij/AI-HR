"""AI runtime management service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..repositories.ai_runtime import AIRuntimeRepository
from ..schemas.ai_runtime import (
    RuntimeFeatureFlagRequest,
    RuntimeFeatureFlagResponse,
    RuntimeModelConfigRequest,
    RuntimeModelConfigResponse,
    RuntimePromptRequest,
    RuntimePromptResponse,
)


class AIRuntimeService:
    """Facade for runtime model/prompt/feature-flag operations."""

    def __init__(self, session: Session):
        self._repository = AIRuntimeRepository(session)

    def upsert_feature_flag(self, feature_key: str, payload: RuntimeFeatureFlagRequest) -> RuntimeFeatureFlagResponse:
        entity = self._repository.upsert_feature_flag(
            feature_key=feature_key,
            tenant_id=payload.tenant_id,
            job_id=payload.job_id,
            enabled=payload.enabled,
            rollout_percent=payload.rollout_percent,
            fallback_mode=payload.fallback_mode,
        )
        return RuntimeFeatureFlagResponse(
            feature_key=entity.feature_key,
            tenant_id=entity.tenant_id,
            job_id=entity.job_id,
            enabled=entity.enabled,
            rollout_percent=entity.rollout_percent,
            fallback_mode=entity.fallback_mode,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def get_feature_flag(
        self,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
    ) -> RuntimeFeatureFlagResponse | None:
        entity = self._repository.get_feature_flag(feature_key, tenant_id=tenant_id, job_id=job_id)
        if entity is None:
            return None
        return RuntimeFeatureFlagResponse(
            feature_key=entity.feature_key,
            tenant_id=entity.tenant_id,
            job_id=entity.job_id,
            enabled=entity.enabled,
            rollout_percent=entity.rollout_percent,
            fallback_mode=entity.fallback_mode,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def rollback_feature_flag(
        self,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
    ) -> RuntimeFeatureFlagResponse:
        entity = self._repository.rollback_feature_flag(feature_key=feature_key, tenant_id=tenant_id, job_id=job_id)
        return RuntimeFeatureFlagResponse(
            feature_key=entity.feature_key,
            tenant_id=entity.tenant_id,
            job_id=entity.job_id,
            enabled=entity.enabled,
            rollout_percent=entity.rollout_percent,
            fallback_mode=entity.fallback_mode,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def upsert_model_config(self, task_key: str, payload: RuntimeModelConfigRequest) -> RuntimeModelConfigResponse:
        entity = self._repository.upsert_model_config(
            task_key=task_key,
            provider=payload.provider,
            model_name=payload.model_name,
            temperature_milli=payload.temperature_milli,
            timeout_seconds=payload.timeout_seconds,
            max_retries=payload.max_retries,
            is_active=payload.is_active,
            weight=payload.weight,
        )
        return RuntimeModelConfigResponse(
            task_key=entity.task_key,
            provider=entity.provider,
            model_name=entity.model_name,
            temperature_milli=entity.temperature_milli,
            timeout_seconds=entity.timeout_seconds,
            max_retries=entity.max_retries,
            is_active=entity.is_active,
            weight=entity.weight,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def get_active_model_config(self, task_key: str) -> RuntimeModelConfigResponse | None:
        entity = self._repository.get_active_model_config(task_key)
        if entity is None:
            return None
        return RuntimeModelConfigResponse(
            task_key=entity.task_key,
            provider=entity.provider,
            model_name=entity.model_name,
            temperature_milli=entity.temperature_milli,
            timeout_seconds=entity.timeout_seconds,
            max_retries=entity.max_retries,
            is_active=entity.is_active,
            weight=entity.weight,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def upsert_prompt(self, task_key: str, payload: RuntimePromptRequest) -> RuntimePromptResponse:
        entity = self._repository.upsert_prompt(
            task_key=task_key,
            version=payload.version,
            system_prompt=payload.system_prompt,
            user_template=payload.user_template,
            output_schema=payload.output_schema,
            is_active=payload.is_active,
            created_by=payload.created_by,
        )
        return RuntimePromptResponse(
            task_key=entity.task_key,
            version=entity.version,
            system_prompt=entity.system_prompt,
            user_template=entity.user_template,
            output_schema=entity.output_schema,
            is_active=entity.is_active,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def get_active_prompt(self, task_key: str) -> RuntimePromptResponse | None:
        entity = self._repository.get_active_prompt(task_key)
        if entity is None:
            return None
        return RuntimePromptResponse(
            task_key=entity.task_key,
            version=entity.version,
            system_prompt=entity.system_prompt,
            user_template=entity.user_template,
            output_schema=entity.output_schema,
            is_active=entity.is_active,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def list_prompt_versions(self, task_key: str) -> list[RuntimePromptResponse]:
        entities = self._repository.list_prompt_versions(task_key)
        return [
            RuntimePromptResponse(
                task_key=item.task_key,
                version=item.version,
                system_prompt=item.system_prompt,
                user_template=item.user_template,
                output_schema=item.output_schema,
                is_active=item.is_active,
                created_by=item.created_by,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in entities
        ]

    def activate_prompt(self, task_key: str, version: str) -> RuntimePromptResponse:
        entity = self._repository.activate_prompt(task_key=task_key, version=version)
        return RuntimePromptResponse(
            task_key=entity.task_key,
            version=entity.version,
            system_prompt=entity.system_prompt,
            user_template=entity.user_template,
            output_schema=entity.output_schema,
            is_active=entity.is_active,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def rollback_prompt(self, task_key: str) -> RuntimePromptResponse:
        entity = self._repository.rollback_prompt(task_key=task_key)
        return RuntimePromptResponse(
            task_key=entity.task_key,
            version=entity.version,
            system_prompt=entity.system_prompt,
            user_template=entity.user_template,
            output_schema=entity.output_schema,
            is_active=entity.is_active,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


def get_ai_runtime_service(session: Session) -> AIRuntimeService:
    return AIRuntimeService(session)
