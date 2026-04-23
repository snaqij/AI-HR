"""
岗位配置加载器

负责加载YAML配置文件、处理配置继承、验证配置有效性，并管理配置缓存。
"""

import logging
import time
from pathlib import Path
from typing import Dict, Optional, List

import yaml

from .config_cache import ConfigCache
from .config_validator import RoleConfigValidator
from .exceptions import (
    ConfigNotFoundError,
    ConfigLoadError,
    ConfigInheritanceError,
    ConfigValidationError
)
from .metrics import get_metrics

logger = logging.getLogger(__name__)


class RoleConfigLoader:
    """岗位配置加载器"""
    
    def __init__(
        self,
        config_dir: str = None,
        cache: ConfigCache = None,
        validator: RoleConfigValidator = None,
        enable_validation: bool = True
    ):
        """
        初始化配置加载器
        
        Args:
            config_dir: 配置文件目录，默认为 ai_hr/role_configs
            cache: 配置缓存实例，默认创建新实例
            validator: 配置验证器实例，默认创建新实例
            enable_validation: 是否启用配置验证
        """
        if config_dir is None:
            # 默认配置目录
            current_dir = Path(__file__).parent.parent.parent
            config_dir = current_dir / "role_configs"
        
        self.config_dir = Path(config_dir)
        self.cache = cache or ConfigCache()
        self.validator = validator or RoleConfigValidator()
        self.enable_validation = enable_validation
        self.metrics = get_metrics()
        self._role_file_index: dict[str, Path] = {}
        
        logger.info(
            "config.loader.initialized",
            extra={
                "config_dir": str(self.config_dir),
                "enable_validation": enable_validation
            }
        )
    
    def load_config(self, role_id: str) -> Optional[Dict]:
        """
        加载岗位配置
        
        Args:
            role_id: 岗位ID
        
        Returns:
            配置字典，如果不存在则返回None
        
        Raises:
            ConfigLoadError: 配置加载失败
            ConfigValidationError: 配置验证失败
        """
        start_time = time.time()
        
        try:
            # 检查缓存
            cached_config = self.cache.get(role_id)
            if cached_config is not None:
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.record_load_success(role_id, duration_ms, cache_hit=True)
                logger.debug(
                    "config.load.cache_hit",
                    extra={"role_id": role_id, "duration_ms": duration_ms}
                )
                return cached_config
            
            # 查找配置文件
            config_file = self._find_config_file(role_id)
            if config_file is None:
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.record_load_failure(role_id, "ConfigNotFoundError", duration_ms)
                logger.warning(
                    "config.load.not_found",
                    extra={"role_id": role_id}
                )
                return None
            
            # 加载配置文件
            config = self._load_yaml_file(config_file)
            
            # 处理继承
            if "extends" in config:
                config = self._apply_inheritance(config, role_id)
            
            # 验证配置
            if self.enable_validation:
                self.validator.raise_if_invalid(config, role_id, str(config_file))
                self.metrics.record_validation_success(role_id)
            
            # 写入缓存
            self.cache.set(role_id, config)
            
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_load_success(role_id, duration_ms, cache_hit=False)
            
            logger.info(
                "config.load.success",
                extra={
                    "role_id": role_id,
                    "file_path": str(config_file),
                    "duration_ms": duration_ms,
                    "has_extends": "extends" in config
                }
            )
            
            return config
        
        except ConfigValidationError:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics.record_load_failure(role_id, "ConfigValidationError", duration_ms)
            raise
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.metrics.record_load_failure(role_id, error_msg, duration_ms)
            
            logger.error(
                "config.load.error",
                extra={
                    "role_id": role_id,
                    "error": error_msg,
                    "duration_ms": duration_ms
                },
                exc_info=True
            )
            
            raise ConfigLoadError(role_id, str(e))
    
    def load_base_config(self) -> Dict:
        """
        加载基础配置
        
        Returns:
            基础配置字典
        """
        return self.load_config("_base") or {}

    def load_all_configs(self) -> Dict[str, Dict]:
        """
        加载所有配置文件
        
        Returns:
            {role_id: config} 字典
        """
        configs = {}
        
        # 遍历所有YAML文件
        for yaml_file in self.config_dir.rglob("*.yaml"):
            if yaml_file.stem.startswith("_"):
                continue  # 跳过基础配置
            
            role_id = self._resolve_role_id_from_file(yaml_file) or yaml_file.stem
            try:
                config = self.load_config(role_id)
                if config:
                    configs[role_id] = config
            except Exception as e:
                logger.warning(
                    f"Failed to load config for {role_id}: {e}"
                )
        
        logger.info(
            "config.load_all.complete",
            extra={"config_count": len(configs)}
        )
        
        return configs
    
    def reload_config(self, role_id: str) -> Dict:
        """
        重新加载配置（清除缓存后加载）
        
        Args:
            role_id: 岗位ID
        
        Returns:
            配置字典
        """
        self.cache.invalidate(role_id)
        return self.load_config(role_id)
    
    def _find_config_file(self, role_id: str) -> Optional[Path]:
        """
        查找配置文件
        
        Args:
            role_id: 岗位ID
        
        Returns:
            配置文件路径，如果不存在则返回None
        """
        # 尝试直接路径
        direct_path = self.config_dir / f"{role_id}.yaml"
        if direct_path.exists():
            return direct_path
        
        # 尝试在子目录中查找
        for subdir in ["tech", "product", "design", "business"]:
            subdir_path = self.config_dir / subdir / f"{role_id}.yaml"
            if subdir_path.exists():
                return subdir_path

        if not self._role_file_index:
            self._build_role_file_index()

        return self._role_file_index.get(role_id)

    def _build_role_file_index(self) -> None:
        """Build a fallback index from role.id to YAML path."""
        index: dict[str, Path] = {}
        for yaml_file in self.config_dir.rglob("*.yaml"):
            role_id = self._resolve_role_id_from_file(yaml_file)
            if role_id:
                index[role_id] = yaml_file
        self._role_file_index = index

    def _resolve_role_id_from_file(self, file_path: Path) -> str | None:
        """Read the top-level role.id for resilient role_id -> file lookup."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            return None
        if not isinstance(config, dict):
            return None
        role = config.get("role", {})
        if not isinstance(role, dict):
            return None
        role_id = str(role.get("id") or "").strip()
        return role_id or None
    
    def _load_yaml_file(self, file_path: Path) -> Dict:
        """
        加载YAML文件
        
        Args:
            file_path: 文件路径
        
        Returns:
            配置字典
        
        Raises:
            ConfigLoadError: 文件加载失败
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not isinstance(config, dict):
                raise ConfigLoadError(
                    file_path.stem,
                    "Configuration must be a dictionary",
                    str(file_path)
                )
            
            return config
        
        except yaml.YAMLError as e:
            raise ConfigLoadError(
                file_path.stem,
                f"YAML parsing error: {str(e)}",
                str(file_path)
            )
        except Exception as e:
            raise ConfigLoadError(
                file_path.stem,
                f"File read error: {str(e)}",
                str(file_path)
            )
    
    def _apply_inheritance(self, config: Dict, role_id: str) -> Dict:
        """
        应用配置继承
        
        Args:
            config: 子配置
            role_id: 岗位ID
        
        Returns:
            合并后的配置
        
        Raises:
            ConfigInheritanceError: 继承失败
        """
        parent_id = config.get("extends")
        if not parent_id:
            return config
        
        try:
            # 加载父配置
            parent_config = self.load_config(parent_id)
            if parent_config is None:
                raise ConfigInheritanceError(
                    role_id,
                    parent_id,
                    "Parent configuration not found"
                )
            
            # 深度合并配置
            merged_config = self._deep_merge(parent_config, config)
            
            logger.debug(
                "config.inheritance.applied",
                extra={
                    "role_id": role_id,
                    "parent_id": parent_id
                }
            )
            
            return merged_config
        
        except ConfigInheritanceError:
            raise
        except Exception as e:
            raise ConfigInheritanceError(
                role_id,
                parent_id,
                str(e)
            )
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        深度合并两个字典
        
        Args:
            base: 基础字典
            override: 覆盖字典
        
        Returns:
            合并后的字典
        """
        result = base.copy()
        
        for key, value in override.items():
            if key == "extends":
                # 不继承extends字段
                continue
            
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 递归合并字典
                result[key] = self._deep_merge(result[key], value)
            else:
                # 直接覆盖
                result[key] = value
        
        return result
