"""Role config loader.

Loads YAML config files, handles config inheritance, validates configs,
and manages the config cache.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Optional

import yaml
from .config_cache import ConfigCache
from .config_validator import RoleConfigValidator
from .exceptions import (
    ConfigInheritanceError,
    ConfigLoadError,
    ConfigValidationError,
)
from .metrics import get_metrics

logger = logging.getLogger(__name__)


class RoleConfigLoader:
    """Role configuration loader."""
    
    def __init__(
        self,
        config_dir: str = None,
        cache: ConfigCache = None,
        validator: RoleConfigValidator = None,
        enable_validation: bool = True
    ):
        """
        Initialize the config loader.
        
        Args:
            config_dir: Config file directory, defaults to ai_hr/role_configs
            cache: Config cache instance, creates a new one if not provided
            validator: Config validator instance, creates a new one if not provided
            enable_validation: Whether to enable config validation
        """
        if config_dir is None:
            # Default config directory
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
        Load a role configuration.
        
        Args:
            role_id: Role ID
        
        Returns:
            Config dict, or None if not found
        
        Raises:
            ConfigLoadError: Config loading failed
            ConfigValidationError: Config validation failed
        """
        start_time = time.time()
        
        try:
            # Check cache
            cached_config = self.cache.get(role_id)
            if cached_config is not None:
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.record_load_success(role_id, duration_ms, cache_hit=True)
                logger.debug(
                    "config.load.cache_hit",
                    extra={"role_id": role_id, "duration_ms": duration_ms}
                )
                return cached_config
            
            # Find config file
            config_file = self._find_config_file(role_id)
            if config_file is None:
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.record_load_failure(role_id, "ConfigNotFoundError", duration_ms)
                logger.warning(
                    "config.load.not_found",
                    extra={"role_id": role_id}
                )
                return None
            
            # Load config file
            config = self._load_yaml_file(config_file)
            
            # Apply inheritance
            if "extends" in config:
                config = self._apply_inheritance(config, role_id)
            
            # Validate config
            if self.enable_validation:
                self.validator.raise_if_invalid(config, role_id, str(config_file))
                self.metrics.record_validation_success(role_id)
            
            # Write to cache
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
        Load the base configuration.
        
        Returns:
            Base config dict
        """
        return self.load_config("_base") or {}

    def load_all_configs(self) -> Dict[str, Dict]:
        """
        Load all config files.
        
        Returns:
            Dict of {role_id: config}
        """
        configs = {}
        
        # Iterate over all YAML files
        for yaml_file in self.config_dir.rglob("*.yaml"):
            if yaml_file.stem.startswith("_"):
                continue  # Skip base configs
            
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
        Reload a config (clears cache then loads).
        
        Args:
            role_id: Role ID
        
        Returns:
            Config dict
        """
        self.cache.invalidate(role_id)
        return self.load_config(role_id)
    
    def _find_config_file(self, role_id: str) -> Optional[Path]:
        """
        Find the config file for a role.
        
        Args:
            role_id: Role ID
        
        Returns:
            Path to the config file, or None if not found
        """
        # Try direct path
        direct_path = self.config_dir / f"{role_id}.yaml"
        if direct_path.exists():
            return direct_path
        
        # Try subdirectories
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
        Load a YAML file.
        
        Args:
            file_path: File path
        
        Returns:
            Config dict
        
        Raises:
            ConfigLoadError: File loading failed
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
        Apply config inheritance.
        
        Args:
            config: Child config
            role_id: Role ID
        
        Returns:
            Merged config
        
        Raises:
            ConfigInheritanceError: Inheritance failed
        """
        parent_id = config.get("extends")
        if not parent_id:
            return config
        
        try:
            # Load parent config
            parent_config = self.load_config(parent_id)
            if parent_config is None:
                raise ConfigInheritanceError(
                    role_id,
                    parent_id,
                    "Parent configuration not found"
                )
            
            # Deep-merge configs
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
        Deep-merge two dicts.
        
        Args:
            base: Base dict
            override: Override dict
        
        Returns:
            Merged dict
        """
        result = base.copy()
        
        for key, value in override.items():
            if key == "extends":
                # Do not inherit the extends field
                continue
            
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                # Direct override
                result[key] = value
        
        return result
