"""Role strategy service.

Provides role config loading, validation, caching, and role identification.
"""

from __future__ import annotations

from .competency_mapper import CompetencyMapper, CompetencyModel, CompetencyWeight
from .config_cache import ConfigCache
from .config_loader import RoleConfigLoader
from .config_validator import RoleConfigValidator
from .exceptions import (
    CacheError,
    ConfigInheritanceError,
    ConfigLoadError,
    ConfigNotFoundError,
    ConfigValidationError,
    RoleConfigError,
)
from .metrics import ConfigMetrics, get_metrics
from .role_profiler import RoleMatch, RoleProfileResult, RoleProfiler

__all__ = [
    "ConfigCache",
    "RoleConfigLoader",
    "RoleConfigValidator",
    "RoleProfiler",
    "RoleMatch",
    "RoleProfileResult",
    "CompetencyMapper",
    "CompetencyModel",
    "CompetencyWeight",
    "RoleConfigError",
    "ConfigNotFoundError",
    "ConfigLoadError",
    "ConfigValidationError",
    "ConfigInheritanceError",
    "CacheError",
    "ConfigMetrics",
    "get_metrics"
]
