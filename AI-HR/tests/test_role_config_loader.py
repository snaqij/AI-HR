"""
岗位配置加载器单元测试
"""

import pytest
import tempfile
from pathlib import Path
from ai_hr.services.role_strategy.config_loader import RoleConfigLoader
from ai_hr.services.role_strategy.config_cache import ConfigCache
from ai_hr.services.role_strategy.exceptions import (
    ConfigLoadError,
    ConfigValidationError,
    ConfigInheritanceError
)


class TestRoleConfigLoader:
    """配置加载器测试"""
    
    @pytest.fixture
    def temp_config_dir(self):
        """创建临时配置目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # 创建基础配置
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
            
            # 创建tech子目录
            tech_dir = config_dir / "tech"
            tech_dir.mkdir()
            
            # 创建后端工程师配置
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
            enable_validation=False  # 简化测试
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
        
        # 应该继承基础配置的universal_competencies
        assert "universal_competencies" in config
        assert "ownership" in config["universal_competencies"]
        
        # 应该有自己的role_competencies
        assert "role_competencies" in config
        assert "technical_depth" in config["role_competencies"]
    
    def test_load_nonexistent_config(self, loader):
        """测试加载不存在的配置"""
        config = loader.load_config("nonexistent_role")
        assert config is None
    
    def test_cache_hit(self, loader):
        """测试缓存命中"""
        # 第一次加载
        config1 = loader.load_config("backend_engineer")
        
        # 第二次加载应该从缓存获取
        config2 = loader.load_config("backend_engineer")
        
        assert config1 == config2
        
        # 检查缓存统计
        stats = loader.cache.get_stats()
        assert stats["hits"] >= 1
    
    def test_reload_config(self, loader):
        """测试重新加载配置"""
        # 第一次加载
        config1 = loader.load_config("backend_engineer")
        
        # 重新加载
        config2 = loader.reload_config("backend_engineer")
        
        assert config1 == config2
        
        # 缓存应该被清除
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
        assert result["b"]["c"] == 20  # 覆盖
        assert result["b"]["d"] == 3   # 保留
        assert result["b"]["f"] == 4   # 新增
        assert result["g"] == 5        # 新增
    
    def test_find_config_file(self, loader, temp_config_dir):
        """测试查找配置文件"""
        # 查找基础配置
        file_path = loader._find_config_file("_base")
        assert file_path is not None
        assert file_path.name == "_base.yaml"
        
        # 查找子目录中的配置
        file_path = loader._find_config_file("backend_engineer")
        assert file_path is not None
        assert file_path.name == "backend_engineer.yaml"
        
        # 查找不存在的配置
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
