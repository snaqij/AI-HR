"""
岗位配置验证器单元测试
"""

import pytest
from ai_hr.services.role_strategy.config_validator import RoleConfigValidator
from ai_hr.services.role_strategy.exceptions import ConfigValidationError


class TestRoleConfigValidator:
    """配置验证器测试"""
    
    @pytest.fixture
    def validator(self):
        """创建验证器实例"""
        return RoleConfigValidator()
    
    @pytest.fixture
    def valid_config(self):
        """有效的配置"""
        return {
            "version": "1.0",
            "role": {
                "id": "backend_engineer",
                "family": "engineering",
                "display_name": {
                    "zh": "后端工程师",
                    "en": "Backend Engineer"
                },
                "match_rules": {
                    "keywords": ["backend", "后端"],
                    "skills": ["python", "java"]
                }
            },
            "universal_competencies": {
                "ownership": {
                    "weight": 0.5,
                    "description": "主人翁意识"
                },
                "communication": {
                    "weight": 0.5,
                    "description": "沟通能力"
                }
            }
        }
    
    def test_validate_valid_config(self, validator, valid_config):
        """测试验证有效配置"""
        is_valid, errors = validator.validate(valid_config)
        assert is_valid
        assert len(errors) == 0
    
    def test_validate_missing_role(self, validator):
        """测试缺少role字段"""
        config = {"version": "1.0"}
        is_valid, errors = validator.validate(config)
        assert not is_valid
        assert any("role" in err.lower() for err in errors)
    
    def test_validate_invalid_role_id(self, validator, valid_config):
        """测试无效的role_id"""
        valid_config["role"]["id"] = "invalid-id!"
        is_valid, errors = validator.validate(valid_config)
        assert not is_valid
        assert any("role.id" in err for err in errors)
    
    def test_validate_missing_display_name(self, validator, valid_config):
        """测试缺少display_name"""
        del valid_config["role"]["display_name"]["zh"]
        is_valid, errors = validator.validate(valid_config)
        assert not is_valid
        assert any("display_name" in err for err in errors)
    
    def test_validate_weight_sum_invalid(self, validator, valid_config):
        """测试权重总和不为1"""
        valid_config["universal_competencies"]["ownership"]["weight"] = 0.3
        valid_config["universal_competencies"]["communication"]["weight"] = 0.3
        is_valid, errors = validator.validate(valid_config)
        assert not is_valid
        assert any("sum to 1.0" in err for err in errors)
    
    def test_validate_weight_sum_valid_with_tolerance(self, validator, valid_config):
        """测试权重总和在容差范围内"""
        valid_config["universal_competencies"]["ownership"]["weight"] = 0.501
        valid_config["universal_competencies"]["communication"]["weight"] = 0.499
        is_valid, errors = validator.validate(valid_config)
        assert is_valid
    
    def test_raise_if_invalid(self, validator, valid_config):
        """测试raise_if_invalid方法"""
        # 有效配置不应抛出异常
        validator.raise_if_invalid(valid_config, "test_role")
        
        # 无效配置应抛出异常
        del valid_config["role"]["display_name"]
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.raise_if_invalid(valid_config, "test_role")
        
        assert exc_info.value.role_id == "test_role"
        assert len(exc_info.value.errors) > 0
    
    def test_validate_empty_keywords(self, validator, valid_config):
        """测试空的keywords数组"""
        valid_config["role"]["match_rules"]["keywords"] = []
        is_valid, errors = validator.validate(valid_config)
        assert not is_valid
        assert any("keywords" in err for err in errors)
