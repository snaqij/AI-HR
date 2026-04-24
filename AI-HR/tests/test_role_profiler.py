"""Unit tests for RoleProfiler."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ai_hr.services.role_strategy.config_loader import RoleConfigLoader
from ai_hr.services.role_strategy.role_profiler import RoleProfiler


class TestRoleProfiler:
    """Tests for RoleProfiler."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create base config
            base_config = """
version: "1.0"
role:
  id: "_base"
  family: "general"
  display_name:
    zh: "Base"
    en: "Base Config"
"""
            (config_dir / "_base.yaml").write_text(base_config, encoding='utf-8')
            
            # Create tech subdirectory
            tech_dir = config_dir / "tech"
            tech_dir.mkdir()
            
            # Create backend engineer config
            backend_config = """
version: "1.0"
role:
  id: "backend_engineer"
  family: "engineering"
  display_name:
    zh: "Backend Engineer"
    en: "Backend Engineer"
  match_rules:
    keywords: ["backend", "java"]
    skills: ["spring", "mysql", "redis"]
"""
            (tech_dir / "backend_engineer.yaml").write_text(backend_config, encoding='utf-8')
            
            # Create frontend engineer config
            frontend_config = """
version: "1.0"
role:
  id: "frontend_engineer"
  family: "engineering"
  display_name:
    zh: "Frontend Engineer"
    en: "Frontend Engineer"
  match_rules:
    keywords: ["frontend", "react"]
    skills: ["react", "vue", "javascript"]
"""
            (tech_dir / "frontend_engineer.yaml").write_text(frontend_config, encoding='utf-8')
            
            yield config_dir
    
    @pytest.fixture
    def profiler(self, temp_config_dir):
        """Create a RoleProfiler instance."""
        loader = RoleConfigLoader(
            config_dir=str(temp_config_dir),
            enable_validation=False
        )
        return RoleProfiler(config_loader=loader)
    
    def test_identify_with_explicit_role_id(self, profiler):
        """Test identifying a role by explicit role ID."""
        config = profiler.identify_role(
            explicit_role_id="backend_engineer"
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_job_title_keyword(self, profiler):
        """Test identifying a role by job title keyword."""
        config = profiler.identify_role(
            job_title="Java backend engineer"
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_skills(self, profiler):
        """Test identifying a role by skill tags."""
        config = profiler.identify_role(
            job_title="engineer",
            skills=["spring", "mysql"]
        )
        
        assert config is not None
        assert config["role"]["id"] == "backend_engineer"
    
    def test_identify_by_jd(self, profiler):
        """Test identifying a role from a job description."""
        config = profiler.identify_role(
            jd="We need a frontend engineer familiar with React and Vue"
        )
        
        assert config is not None
        assert config["role"]["id"] == "frontend_engineer"
    
    def test_identify_fallback_to_base(self, profiler):
        """Test fallback to base config when no role matches."""
        config = profiler.identify_role(
            job_title="unknown position"
        )
        
        assert config is not None
        assert config["role"]["id"] == "_base"
    
    def test_calculate_match_score(self, profiler):
        """Test match score calculation."""
        match_rules = {
            "keywords": ["backend", "java"],
            "skills": ["spring", "mysql"]
        }
        
        score, details = profiler._calculate_match_score(
            text="Java Backend Engineer",
            skills=["spring", "redis"],
            match_rules=match_rules
        )
        
        # Should match 2 keywords (backend, java) = 4 points
        # Should match 1 skill (spring) = 1 point
        # Total = 5
        assert score == 5.0
        assert len(details["keyword_matches"]) == 2
        assert len(details["skill_matches"]) == 1
    
    def test_best_match_selection(self, profiler):
        """Test selecting the best match"""
        # When matching multiple roles, should select the one with highest score
        config = profiler.identify_role(
            job_title="Full Stack Engineer with React and Java",
            skills=["react", "spring"]
        )
        
        # Should match one of the roles
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
