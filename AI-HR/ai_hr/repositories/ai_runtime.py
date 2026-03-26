"""AI runtime config repository."""

from __future__ import annotations

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from ..db.models import AIFeatureFlag, AIModelConfig, AIPromptVersion
from ..core.exceptions import ResourceNotFoundError


class AIRuntimeRepository:
    """Read/write model routes, prompts and feature flags."""

    def __init__(self, session: Session):
        self._session = session

    def get_active_model_config(self, task_key: str) -> AIModelConfig | None:
        stmt = (
            select(AIModelConfig)
            .where(AIModelConfig.task_key == task_key, AIModelConfig.is_active.is_(True))
            .order_by(desc(AIModelConfig.weight), desc(AIModelConfig.updated_at))
        )
        return self._session.execute(stmt).scalars().first()

    def upsert_model_config(
        self,
        *,
        task_key: str,
        provider: str,
        model_name: str,
        temperature_milli: int,
        timeout_seconds: int,
        max_retries: int,
        is_active: bool,
        weight: int,
    ) -> AIModelConfig:
        stmt = (
            select(AIModelConfig)
            .where(AIModelConfig.task_key == task_key, AIModelConfig.provider == provider, AIModelConfig.model_name == model_name)
            .order_by(desc(AIModelConfig.updated_at))
        )
        entity = self._session.execute(stmt).scalars().first()
        if entity is None:
            entity = AIModelConfig(
                task_key=task_key,
                provider=provider,
                model_name=model_name,
                temperature_milli=temperature_milli,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                is_active=is_active,
                weight=weight,
            )
            self._session.add(entity)
        else:
            entity.temperature_milli = temperature_milli
            entity.timeout_seconds = timeout_seconds
            entity.max_retries = max_retries
            entity.is_active = is_active
            entity.weight = weight
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def get_active_prompt(self, task_key: str) -> AIPromptVersion | None:
        stmt = (
            select(AIPromptVersion)
            .where(AIPromptVersion.task_key == task_key, AIPromptVersion.is_active.is_(True))
            .order_by(desc(AIPromptVersion.updated_at))
        )
        return self._session.execute(stmt).scalars().first()

    def upsert_prompt(
        self,
        *,
        task_key: str,
        version: str,
        system_prompt: str,
        user_template: str,
        output_schema: dict,
        is_active: bool,
        created_by: str | None,
    ) -> AIPromptVersion:
        stmt = select(AIPromptVersion).where(AIPromptVersion.task_key == task_key, AIPromptVersion.version == version)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            entity = AIPromptVersion(
                task_key=task_key,
                version=version,
                system_prompt=system_prompt,
                user_template=user_template,
                output_schema=output_schema,
                is_active=is_active,
                created_by=created_by,
            )
            self._session.add(entity)
        else:
            entity.system_prompt = system_prompt
            entity.user_template = user_template
            entity.output_schema = output_schema
            entity.is_active = is_active
            entity.created_by = created_by
        if is_active:
            self._session.execute(
                update(AIPromptVersion)
                .where(
                    AIPromptVersion.task_key == task_key,
                    AIPromptVersion.version != version,
                )
                .values(is_active=False)
            )
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def list_prompt_versions(self, task_key: str) -> list[AIPromptVersion]:
        stmt = (
            select(AIPromptVersion)
            .where(AIPromptVersion.task_key == task_key)
            .order_by(desc(AIPromptVersion.updated_at), desc(AIPromptVersion.created_at))
        )
        return self._session.execute(stmt).scalars().all()

    def activate_prompt(self, *, task_key: str, version: str) -> AIPromptVersion:
        target = self._session.execute(
            select(AIPromptVersion).where(
                AIPromptVersion.task_key == task_key,
                AIPromptVersion.version == version,
            )
        ).scalar_one_or_none()
        if target is None:
            raise ResourceNotFoundError(f"Prompt version not found for task='{task_key}' version='{version}'")
        self._session.execute(
            update(AIPromptVersion).where(AIPromptVersion.task_key == task_key).values(is_active=False)
        )
        target.is_active = True
        self._session.commit()
        self._session.refresh(target)
        return target

    def rollback_prompt(self, *, task_key: str) -> AIPromptVersion:
        versions = self.list_prompt_versions(task_key)
        if not versions:
            raise ResourceNotFoundError(f"No prompt versions found for task='{task_key}'")
        active_index = next((idx for idx, item in enumerate(versions) if item.is_active), 0)
        rollback_index = min(active_index + 1, len(versions) - 1)
        target = versions[rollback_index]
        return self.activate_prompt(task_key=task_key, version=target.version)

    def get_feature_flag(
        self,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
    ) -> AIFeatureFlag | None:
        """Fetch exact feature flag by feature/tenant/job scope."""
        stmt = (
            select(AIFeatureFlag)
            .where(
                AIFeatureFlag.feature_key == feature_key,
                AIFeatureFlag.tenant_id == tenant_id,
                AIFeatureFlag.job_id == job_id,
            )
            .execution_options(populate_existing=True)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def resolve_feature_flag(
        self,
        *,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
    ) -> tuple[AIFeatureFlag | None, str]:
        """Resolve by precedence: tenant+job -> tenant -> global -> default."""
        if tenant_id and job_id:
            matched = self.get_feature_flag(feature_key, tenant_id=tenant_id, job_id=job_id)
            if matched is not None:
                return matched, "tenant_job"
        if tenant_id:
            matched = self.get_feature_flag(feature_key, tenant_id=tenant_id, job_id=None)
            if matched is not None:
                return matched, "tenant"
        matched = self.get_feature_flag(feature_key, tenant_id=None, job_id=None)
        if matched is not None:
            return matched, "global"
        return None, "default"

    def upsert_feature_flag(
        self,
        *,
        feature_key: str,
        tenant_id: str | None,
        job_id: str | None,
        enabled: bool,
        rollout_percent: int,
        fallback_mode: str,
    ) -> AIFeatureFlag:
        entity = self.get_feature_flag(feature_key, tenant_id=tenant_id, job_id=job_id)
        if entity is None:
            entity = AIFeatureFlag(
                feature_key=feature_key,
                tenant_id=tenant_id,
                job_id=job_id,
                enabled=enabled,
                rollout_percent=rollout_percent,
                fallback_mode=fallback_mode,
            )
            self._session.add(entity)
        else:
            entity.enabled = enabled
            entity.rollout_percent = rollout_percent
            entity.fallback_mode = fallback_mode
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def rollback_feature_flag(
        self,
        *,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
    ) -> AIFeatureFlag:
        return self.upsert_feature_flag(
            feature_key=feature_key,
            tenant_id=tenant_id,
            job_id=job_id,
            enabled=False,
            rollout_percent=0,
            fallback_mode="rule_only",
        )

    def is_feature_enabled(
        self,
        *,
        feature_key: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
        default_enabled: bool = False,
    ) -> bool:
        flag, _ = self.resolve_feature_flag(feature_key=feature_key, tenant_id=tenant_id, job_id=job_id)
        if flag is None:
            return default_enabled
        if flag.fallback_mode == "rule_only":
            return False
        return bool(flag.enabled and flag.rollout_percent > 0)
