"""Role config exceptions.

Exception hierarchy for the role configuration system.
"""

from __future__ import annotations


class RoleConfigError(Exception):
    """Base exception for role configuration errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class ConfigNotFoundError(RoleConfigError):
    """Raised when a config file does not exist."""

    def __init__(self, role_id: str, file_path: str = None):
        details = {"role_id": role_id}
        if file_path:
            details["file_path"] = file_path
        super().__init__(
            f"Configuration not found for role: {role_id}",
            details
        )
        self.role_id = role_id
        self.file_path = file_path


class ConfigLoadError(RoleConfigError):
    """Raised when a config file fails to load."""

    def __init__(self, role_id: str, reason: str, file_path: str = None):
        details = {"role_id": role_id, "reason": reason}
        if file_path:
            details["file_path"] = file_path
        super().__init__(
            f"Failed to load configuration for role: {role_id}",
            details
        )
        self.role_id = role_id
        self.reason = reason
        self.file_path = file_path


class ConfigValidationError(RoleConfigError):
    """Raised when a config fails validation."""

    def __init__(self, role_id: str, errors: list, file_path: str = None):
        details = {"role_id": role_id, "error_count": len(errors)}
        if file_path:
            details["file_path"] = file_path

        error_messages = "\n  - ".join(errors)
        super().__init__(
            f"Configuration validation failed for role: {role_id}\n  - {error_messages}",
            details
        )
        self.role_id = role_id
        self.errors = errors
        self.file_path = file_path


class ConfigInheritanceError(RoleConfigError):
    """Raised when config inheritance fails."""

    def __init__(self, role_id: str, parent_id: str, reason: str):
        super().__init__(
            f"Failed to inherit configuration from '{parent_id}' for role '{role_id}': {reason}",
            {"role_id": role_id, "parent_id": parent_id, "reason": reason}
        )
        self.role_id = role_id
        self.parent_id = parent_id
        self.reason = reason


class CacheError(RoleConfigError):
    """Raised when a cache operation fails."""

    def __init__(self, operation: str, reason: str):
        super().__init__(
            f"Cache operation '{operation}' failed: {reason}",
            {"operation": operation, "reason": reason}
        )
        self.operation = operation
        self.reason = reason
