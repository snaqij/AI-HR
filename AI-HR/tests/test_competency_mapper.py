"""
能力映射器单元测试
"""

import pytest
from ai_hr.services.role_strategy import CompetencyMapper, RoleConfigLoader


@pytest.fixture
def mapper():
    """创建能力映射器实例"""
    return CompetencyMapper()


@pytest.fixture
def backend_config():
    """加载后端工程师配置"""
    loader = RoleConfigLoader()
    return loader.load_config("backend_engineer")


def test_build_competency_model(mapper, backend_config):
    """测试构建能力模型"""
    model = mapper.build_competency_model(backend_config)
    
    assert model.role_id == "backend_engineer"
    assert len(model.universal_competencies) > 0
    assert len(model.role_competencies) > 0
    assert model.total_weight > 0


def test_calculate_competency_weights(mapper, backend_config):
    """测试计算能力权重"""
    weights = mapper.calculate_competency_weights(backend_config, normalize=False)
    
    assert isinstance(weights, dict)
    assert len(weights) > 0
    assert all(isinstance(w, float) for w in weights.values())
    
    # 测试归一化
    normalized_weights = mapper.calculate_competency_weights(backend_config, normalize=True)
    total = sum(normalized_weights.values())
    assert abs(total - 1.0) < 0.01  # 允许浮点误差


def test_get_evidence_requirements(mapper, backend_config):
    """测试获取证据要求"""
    evidence_map = mapper.get_evidence_requirements(backend_config)
    
    assert isinstance(evidence_map, dict)
    assert len(evidence_map) > 0
    assert all(isinstance(v, list) for v in evidence_map.values())


def test_validate_competency_config(mapper, backend_config):
    """测试验证能力配置"""
    is_valid, errors = mapper.validate_competency_config(backend_config)
    
    assert is_valid is True
    assert len(errors) == 0


def test_validate_invalid_config(mapper):
    """测试验证无效配置"""
    invalid_config = {
        "role": {"id": "test"},
        "universal_competencies": {
            "test_comp": {
                "weight": -0.5,  # 负权重
                "description": "Test",
                "evidence_types": []  # 空证据类型
            }
        },
        "role_competencies": {}
    }
    
    is_valid, errors = mapper.validate_competency_config(invalid_config)
    
    assert is_valid is False
    assert len(errors) > 0


def test_competency_model_methods(mapper, backend_config):
    """测试能力模型的方法"""
    model = mapper.build_competency_model(backend_config)
    
    # 测试获取所有能力
    all_comps = model.get_all_competencies()
    assert len(all_comps) == len(model.universal_competencies) + len(model.role_competencies)
    
    # 测试根据ID获取能力
    if all_comps:
        first_comp = all_comps[0]
        found_comp = model.get_competency_by_id(first_comp.competency_id)
        assert found_comp is not None
        assert found_comp.competency_id == first_comp.competency_id
    
    # 测试获取证据类型
    evidence_types = model.get_evidence_types()
    assert isinstance(evidence_types, list)
    assert len(evidence_types) > 0


def test_empty_config(mapper):
    """测试空配置"""
    with pytest.raises(ValueError):
        mapper.build_competency_model(None)
    
    with pytest.raises(ValueError):
        mapper.build_competency_model({})
