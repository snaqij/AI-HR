"""LLM model/prompt routing."""

from __future__ import annotations

from dataclasses import dataclass

from ...core.config import Settings, get_settings
from ...core.exceptions import AIHRException
from ...repositories.ai_runtime import AIRuntimeRepository
from .prompts import get_prompt_template


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """Resolved routing result for a task."""

    provider: str
    model_name: str
    timeout_seconds: int
    max_retries: int
    temperature_milli: int
    prompt_version: str


class ModelRouter:
    """Resolve model/prompt route by runtime config, then settings fallback."""

    def __init__(
        self,
        runtime_repository: AIRuntimeRepository | None = None,
        settings: Settings | None = None,
    ):
        self._runtime_repository = runtime_repository
        self._settings = settings or get_settings()

    def _is_production(self) -> bool:
        return (self._settings.environment or "").strip().lower() in {"prod", "production"}

    def _ensure_route_allowed(self, *, task_key: str, route: ModelRoute) -> ModelRoute:
        if self._is_production() and route.provider.strip().lower() == "mock":
            raise AIHRException(
                f"LLM route for task '{task_key}' resolved to mock provider in production; "
                "please configure active runtime model/prompt or AI_HR_LLM_PROVIDER + AI_HR_LLM_MODEL."
            )
        return route

    def resolve_route(self, task_key: str) -> ModelRoute:
        """Resolve route for task_key with safe production fallback."""
        prompt_version = "v1"
        if self._runtime_repository is not None:
            model_config = self._runtime_repository.get_active_model_config(task_key)
            prompt_config = self._runtime_repository.get_active_prompt(task_key)
            if prompt_config:
                prompt_version = prompt_config.version
            if model_config and prompt_config:
                return self._ensure_route_allowed(
                    task_key=task_key,
                    route=ModelRoute(
                        provider=model_config.provider,
                        model_name=model_config.model_name,
                        timeout_seconds=model_config.timeout_seconds,
                        max_retries=model_config.max_retries,
                        temperature_milli=model_config.temperature_milli,
                        prompt_version=prompt_config.version,
                    ),
                )

        # Ensure template exists for fallback prompt version.
        _ = get_prompt_template(task_key, prompt_version)

        provider = (self._settings.llm_provider or "mock").strip().lower()
        model_name = (self._settings.llm_model or "").strip()
        if provider != "mock" and model_name:
            return self._ensure_route_allowed(
                task_key=task_key,
                route=ModelRoute(
                    provider=provider,
                    model_name=model_name,
                    timeout_seconds=max(1, int(self._settings.llm_timeout_seconds)),
                    max_retries=max(0, int(self._settings.llm_max_retries)),
                    temperature_milli=200,
                    prompt_version=prompt_version,
                ),
            )

        return self._ensure_route_allowed(
            task_key=task_key,
            route=ModelRoute(
                provider="mock",
                model_name=f"{task_key}-mock",
                timeout_seconds=8,
                max_retries=1,
                temperature_milli=200,
                prompt_version=prompt_version,
            ),
        )
