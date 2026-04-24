"""外部 Provider 熔断器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class ProviderCircuitState:
    """记录单个 Provider 熔断状态。"""

    fail_count: int = 0
    opened_until: datetime | None = None
    last_error: str | None = None


class ProviderCircuitBreaker:
    """进程内 Provider 熔断控制器。"""

    def __init__(self, *, fail_threshold: int, cooldown_seconds: int):
        self._fail_threshold = max(1, fail_threshold)
        self._cooldown_seconds = max(1, cooldown_seconds)
        self._states: dict[str, ProviderCircuitState] = {}

    def _state(self, provider_key: str) -> ProviderCircuitState:
        if provider_key not in self._states:
            self._states[provider_key] = ProviderCircuitState()
        return self._states[provider_key]

    def allow(self, provider_key: str) -> bool:
        """当前是否允许请求通过。"""
        state = self._state(provider_key)
        if state.opened_until is None:
            return True
        now = datetime.now(UTC).replace(tzinfo=None)
        if now >= state.opened_until:
            state.opened_until = None
            state.fail_count = 0
            state.last_error = None
            return True
        return False

    def on_success(self, provider_key: str) -> None:
        """请求成功后重置失败计数。"""
        state = self._state(provider_key)
        state.fail_count = 0
        state.opened_until = None
        state.last_error = None

    def on_failure(self, provider_key: str, *, error_message: str) -> None:
        """请求失败后累加计数并按阈值熔断。"""
        state = self._state(provider_key)
        state.fail_count += 1
        state.last_error = error_message[:300]
        if state.fail_count >= self._fail_threshold:
            now = datetime.now(UTC).replace(tzinfo=None)
            state.opened_until = now + timedelta(seconds=self._cooldown_seconds)

    def snapshot(self, provider_key: str) -> dict[str, str | int | bool | None]:
        """返回当前 provider 熔断快照。"""
        state = self._state(provider_key)
        now = datetime.now(UTC).replace(tzinfo=None)
        opened = state.opened_until is not None and state.opened_until > now
        return {
            "opened": opened,
            "fail_count": state.fail_count,
            "opened_until": state.opened_until.isoformat() if state.opened_until else None,
            "last_error": state.last_error,
        }
