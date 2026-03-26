"""Connector registry."""

from __future__ import annotations

from collections.abc import Callable

from .base import ConnectorCredentials, RecruitingConnector
from .boss import BossConnector
from ..core.exceptions import ConnectorNotFoundError

ConnectorFactory = Callable[[ConnectorCredentials], RecruitingConnector]


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ConnectorFactory] = {}

    def register(self, channel: str, factory: ConnectorFactory) -> None:
        self._factories[channel] = factory

    def create(self, channel: str, credentials: ConnectorCredentials) -> RecruitingConnector:
        try:
            factory = self._factories[channel]
        except KeyError as exc:
            raise ConnectorNotFoundError(f"Connector '{channel}' is not registered") from exc
        connector = factory(credentials)
        connector.validate_credentials()
        return connector


registry = ConnectorRegistry()
registry.register("boss", BossConnector)
