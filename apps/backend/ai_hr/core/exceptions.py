"""Domain and infrastructure exceptions."""

from __future__ import annotations


class AIHRException(Exception):
    """Base service exception."""


class ResourceNotFoundError(AIHRException):
    """Raised when resource is missing."""


class InvalidStateError(AIHRException):
    """Raised when state does not satisfy preconditions."""


class ConnectorNotFoundError(AIHRException):
    """Raised when connector is not registered."""


class InvalidConnectorConfigError(AIHRException):
    """Raised when connector configuration is invalid."""


class ConnectorOperationError(AIHRException):
    """Raised when connector operation fails."""


class CredentialsExpiredError(ConnectorOperationError):
    """Raised when connector credentials are expired or invalid."""


class ObjectStorageError(AIHRException):
    """Raised when object storage operation fails."""

