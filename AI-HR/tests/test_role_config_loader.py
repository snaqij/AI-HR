"""Unit tests for RoleConfigLoader."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ai_hr.services.role_strategy.config_cache import ConfigCache
from ai_hr.services.role_strategy.config_loader import RoleConfigLoader
from ai_hr.services.role_strategy.exceptions import (
    ConfigInheritanceError,
    ConfigLoadError,
    ConfigValidationError,
)


class TestRoleConfigLoader:
    """配置加载器测试"""
    
    @pytest.fixture
    def temp_config_dir(self):
        """创建临时配置目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create base config
            base_config = """
version: "1.0"
role:
  id: "_base"
  family: "general"
  display_name:
    zh: "基础配置"
    en: "Base Config"
universal_competencies:
  ownership:
    weight: 0.5
    description: "主人翁意识"
  communication:
    weight: 0.5
    description: "沟通能力"
"""
            (config_dir / "_base.yaml").write_text(base_config, encoding='utf-8')
            
            # Create tech subdirectory
            tech_dir = config_dir / "tech"
            tech_dir.mkdir()
            
            # Create backend engineer config
            backend_config = """
version: "1.0"
extends: "_base"
role:
  id: "backend_engineer"
  family: "engineering"
  display_name:
    zh: "后端工程师"
    en: "Backend Engineer"
  match_rules:
    keywords: ["backend", "后端"]
role_competencies:
  technical_depth:
    weight: 1.0
    description: "技术深度"
"""
            (tech_dir / "backend_engineer.yaml").write_text(backend_config, encoding='utf-8')
            
            yield config_dir
    
    @pytest.fixture
    def loader(self, temp_config_dir):
        """创建加载器实例"""
        cache = ConfigCache(max_size=10, ttl_seconds=60)
        return RoleConfigLoader(
            config_dir=str(temp_config_dir),
            cache=cache,
            enable_validation=False  # Simplify testing
        )
    
    def test_load_base_config(self, loader):
        """测试加载基础配置"""
        config = loader.load_base_config()
        assert config is not None
        assert config["role"]["id"] == "_base"
    
    def test_load_config_with_inheritance(self, loader):
        """测试加载带继承的配置"""
        config = loader.load_config("backend_engineer")
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
        
        # Should inherit universal_competencies from base config
        assert "universal_competencies" in config
        assert "ownership" in config["universal_competencies"]
        
        # Should have its own role_competencies
        assert "role_competencies" in config
        assert "technical_depth" in config["role_competencies"]
    
    def test_load_nonexistent_config(self, loader):
        """测试加载不存在的配置"""
        config = loader.load_config("nonexistent_role")
        assert config is None
    
    def test_cache_hit(self, loader):
        """Test cache hit"""
        # First load
        config1 = loader.load_config("backend_engineer")
        
        # Second load should hit cache
        config2 = loader.load_config("backend_engineer")
        
        assert config1 == config2
        
        # Check cache statistics
        stats = loader.cache.get_stats()
        assert stats["hits"] >= 1
    
    def test_reload_config(self, loader):
        """Test reloading config"""
        # First load
        config1 = loader.load_config("backend_engineer")
        
        # Reload
        config2 = loader.reload_config("backend_engineer")
        
        assert config1 == config2
        
        # Cache should be cleared
        stats = loader.cache.get_stats()
        assert stats["invalidations"] >= 1
    
    def test_deep_merge(self, loader):
        """测试深度合并"""
        base = {
            "a": 1,
            "b": {"c": 2, "d": 3},
            "e": [1, 2]
        }
        override = {
            "b": {"c": 20, "f": 4},
            "g": 5
        }
        
        result = loader._deep_merge(base, override)
        
        assert result["a"] == 1
        assert result["b"]["c"] == 20  # Override
        assert result["b"]["d"] == 3   # Keep
        assert result["b"]["f"] == 4   # New
        assert result["g"] == 5        # New
    
    def test_find_config_file(self, loader, temp_config_dir):
        """Test finding config file"""
        # Find base config
        file_path = loader._find_config_file("_base")
        assert file_path is not None
        assert file_path.name == "_base.yaml"
        
        # Find config in subdirectory
        file_path = loader._find_config_file("backend_engineer")
        assert file_path is not None
        assert file_path.name == "backend_engineer.yaml"
        
        # Find non-existent config
        file_path = loader._find_config_file("nonexistent")
        assert file_path is None


    def test_find_config_file_by_role_id_when_filename_differs(self, temp_config_dir):
        """Role lookup should still succeed when filename and role.id differ."""
        product_dir = temp_config_dir / "product"
        product_dir.mkdir()
        (product_dir / "pm.yaml").write_text(
            """
version: "1.0"
extends: "_base"
role:
  id: "product_manager"
  family: "product"
  display_name:
    zh: "????"
    en: "Product Manager"
""",
            encoding="utf-8",
        )
        loader = RoleConfigLoader(config_dir=str(temp_config_dir), enable_validation=False)
        file_path = loader._find_config_file("product_manager")
        assert file_path is not None
        assert file_path.name == "pm.yaml"
