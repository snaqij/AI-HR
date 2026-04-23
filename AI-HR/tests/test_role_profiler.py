"""
岗位识别器单元测试
"""

import pytest
import tempfile
from pathlib import Path
from ai_hr.services.role_strategy.role_profiler import RoleProfiler
from ai_hr.services.role_strategy.config_loader import RoleConfigLoader


class TestRoleProfiler:
    """岗位识别器测试"""
    
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
"""
            (config_dir / "_base.yaml").write_text(base_config, encoding='utf-8')
            
            # 创建tech子目录
            tech_dir = config_dir / "tech"
            tech_dir.mkdir()
            
            # 创建后端工程师配置
            backend_config = """
version: "1.0"
role:
  id: "backend_engineer"
  family: "engineering"
  display_name:
    zh: "后端工程师"
    en: "Backend Engineer"
  match_rules:
    keywords: ["backend", "后端", "java"]
    skills: ["spring", "mysql", "redis"]
"""
            (tech_dir / "backend_engineer.yaml").write_text(backend_config, encoding='utf-8')
            
            # 创建前端工程师配置
            frontend_config = """
version: "1.0"
role:
  id: "frontend_engineer"
  family: "engineering"
  display_name:
    zh: "前端工程师"
    en: "Frontend Engineer"
  match_rules:
    keywords: ["frontend", "前端", "react"]
    skills: ["react", "vue", "javascript"]
"""
            (tech_dir / "frontend_engineer.yaml").write_text(frontend_config, encoding='utf-8')
            
            yield config_dir
    
    @pytest.fixture
    def profiler(self, temp_config_dir):
        """创建岗位识别器实例"""
        loader = RoleConfigLoader(
            config_dir=str(temp_config_dir),
            enable_validation=False
        )
        return RoleProfiler(config_loader=loader)
    
    def test_identify_with_explicit_role_id(self, profiler):
        """测试明确指定岗位ID"""
        config = profiler.identify_role(
            explicit_role_id="backend_engineer"
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_job_title_keyword(self, profiler):
        """测试通过职位标题关键词识别"""
        config = profiler.identify_role(
            job_title="Java后端工程师"
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_skills(self, profiler):
        """测试通过技能标签识别"""
        config = profiler.identify_role(
            job_title="工程师",
            skills=["spring", "mysql"]
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_jd(self, profiler):
        """测试通过JD识别"""
        config = profiler.identify_role(
            jd="我们需要一名熟悉React和Vue的前端工程师"
        )
        
        assert config is not None
        assert config["role"]["id"] == "frontend_engineer"
    
    def test_identify_fallback_to_base(self, profiler):
        """测试回退到基础配置"""
        config = profiler.identify_role(
            job_title="未知岗位"
        )
        
        assert config is not None
        assert config["role"]["id"] == "_base"
    
    def test_calculate_match_score(self, profiler):
        """测试匹配分数计算"""
        match_rules = {
            "keywords": ["backend", "java"],
            "skills": ["spring", "mysql"]
        }
        
        score, details = profiler._calculate_match_score(
            text="Java Backend Engineer",
            skills=["spring", "redis"],
            match_rules=match_rules
        )
        
        # 应该匹配2个关键词(backend, java) = 4分
        # 应该匹配1个技能(spring) = 1分
        # 总分 = 5
        assert score == 5.0
        assert len(details["keyword_matches"]) == 2
        assert len(details["skill_matches"]) == 1
    
    def test_best_match_selection(self, profiler):
        """测试选择最佳匹配"""
        # 同时匹配多个岗位，应该选择得分最高的
        config = profiler.identify_role(
            job_title="Full Stack Engineer with React and Java",
            skills=["react", "spring"]
        )
        
        # 应该匹配到其中一个岗位
        assert config is not None
        assert config["role"]["id"] in ["backend_engineer", "frontend_engineer"]


    def test_identify_role_profile_metadata(self, profiler):
        """Metadata-rich resolution should report source and score."""
        profile = profiler.identify_role_profile(
            job_title="Java?????",
            skills=["spring", "mysql"],
        )

        assert profile.role_id == "backend_engineer"
        assert profile.source == "auto_match"
        assert profile.score > 0
        assert "keyword_matches" in profile.match_details
