"""
岗位策略服务

提供岗位配置加载、验证、缓存和岗位识别功能。
"""

from .config_cache import ConfigCache
from .config_loader import RoleConfigLoader
from .config_validator import RoleConfigValidator
from .role_profiler import RoleProfiler, RoleMatch, RoleProfileResult
from .competency_mapper import CompetencyMapper, CompetencyModel, CompetencyWeight
from .exceptions import (
    RoleConfigError,
    ConfigNotFoundError,
    ConfigLoadError,
    ConfigValidationError,
    ConfigInheritanceError,
    CacheError
)
from .metrics import ConfigMetrics, get_metrics

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
