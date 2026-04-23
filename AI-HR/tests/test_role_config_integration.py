"""
集成测试：岗位配置与面试流程集成

测试岗位配置如何影响面试流程策略。
"""

import pytest
from ai_hr.services.interview_runtime.flow_policy import (
    get_stage_policy,
    set_role_config_for_session,
    get_role_config_for_session,
    clear_role_config_for_session,
    resolve_followup_limit,
    STAGE_POLICIES,
)
from ai_hr.services.role_strategy import RoleConfigLoader


class TestRoleConfigIntegration:
    """测试岗位配置与面试流程的集成"""
    
    def test_session_role_config_storage(self):
        """测试会话级别的岗位配置存储和检索"""
        session_id = "test_session_123"
        role_config = {
            "role": {"id": "backend_engineer"},
            "followup_strategy": {"max_per_question": 5}
        }
        
        # 存储配置
        set_role_config_for_session(session_id, role_config)
        
        # 检索配置
        retrieved = get_role_config_for_session(session_id)
        assert retrieved is not None
        assert retrieved["role"]["id"] == "backend_engineer"
        assert retrieved["followup_strategy"]["max_per_question"] == 5
        
        # 清除配置
        clear_role_config_for_session(session_id)
        assert get_role_config_for_session(session_id) is None
    
    def test_stage_policy_without_role_config(self):
        """测试没有岗位配置时使用默认策略"""
        session_id = "test_session_no_config"
        
        # 获取S3阶段策略（没有role config）
        policy = get_stage_policy("S3", session_id)
        
        # 应该返回默认策略
        assert policy.code == "S3"
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups
    
    def test_stage_policy_with_role_config_override(self):
        """测试岗位配置覆盖阶段策略"""
        session_id = "test_session_with_config"
        role_config = {
            "role": {"id": "backend_engineer"},
            "followup_strategy": {"max_per_question": 5}
        }
        
        # 存储配置
        set_role_config_for_session(session_id, role_config)
        
        # 获取S3阶段策略（有role config）
        policy = get_stage_policy("S3", session_id)
        
        # max_followups应该被覆盖为5
        assert policy.code == "S3"
        assert policy.max_followups == 5
        
        # 清除配置
        clear_role_config_for_session(session_id)
    
    def test_resolve_followup_limit_priority(self):
        """测试追问限制的优先级顺序"""
        session_id = "test_session_priority"
        role_config = {
            "followup_strategy": {"max_per_question": 5}
        }
        set_role_config_for_session(session_id, role_config)
        
        # 1. 题目特定限制（最高优先级）
        question = {"max_followups": 2}
        limit = resolve_followup_limit(
            stage_code="S3",
            question=question,
            session_id=session_id
        )
        assert limit == 2
        
        # 2. 显式默认值
        limit = resolve_followup_limit(
            stage_code="S3",
            default=3,
            session_id=session_id
        )
        assert limit == 3
        
        # 3. 岗位配置覆盖
        limit = resolve_followup_limit(
            stage_code="S3",
            session_id=session_id
        )
        assert limit == 5
        
        # 4. 阶段策略限制（最低优先级）
        clear_role_config_for_session(session_id)
        limit = resolve_followup_limit(
            stage_code="S3",
            session_id=session_id
        )
        assert limit == STAGE_POLICIES["S3"].max_followups
    
    def test_load_backend_config_and_apply(self):
        """测试加载后端工程师配置并应用到会话"""
        loader = RoleConfigLoader()
        
        # 加载后端工程师配置
        backend_config = loader.load_config("backend_engineer")
        assert backend_config is not None
        assert backend_config["role"]["id"] == "backend_engineer"
        
        # 应用到会话
        session_id = "test_backend_session"
        set_role_config_for_session(session_id, backend_config)
        
        # 验证配置生效
        policy = get_stage_policy("S3", session_id)
        expected_max = backend_config["followup_strategy"]["max_per_question"]
        assert policy.max_followups == expected_max
        
        # 清除
        clear_role_config_for_session(session_id)
    
    def test_multiple_sessions_isolation(self):
        """测试多个会话的配置隔离"""
        session1 = "session_1"
        session2 = "session_2"
        
        config1 = {"followup_strategy": {"max_per_question": 3}}
        config2 = {"followup_strategy": {"max_per_question": 5}}
        
        set_role_config_for_session(session1, config1)
        set_role_config_for_session(session2, config2)
        
        # 验证隔离
        policy1 = get_stage_policy("S3", session1)
        policy2 = get_stage_policy("S3", session2)
        
        assert policy1.max_followups == 3
        assert policy2.max_followups == 5
        
        # 清除
        clear_role_config_for_session(session1)
        clear_role_config_for_session(session2)
    
    def test_invalid_role_config_graceful_fallback(self):
        """测试无效配置时的优雅降级"""
        session_id = "test_invalid_config"
        
        # 设置无效配置（缺少followup_strategy）
        invalid_config = {"role": {"id": "unknown"}}
        set_role_config_for_session(session_id, invalid_config)
        
        # 应该回退到默认策略
        policy = get_stage_policy("S3", session_id)
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups
        
        clear_role_config_for_session(session_id)
    
    def test_empty_session_id_handling(self):
        """测试空session_id的处理"""
        # 空session_id不应该崩溃
        set_role_config_for_session("", {"test": "config"})
        set_role_config_for_session(None, {"test": "config"})
        
        assert get_role_config_for_session("") is None
        assert get_role_config_for_session(None) is None
        
        # 获取策略时不提供session_id应该返回默认策略
        policy = get_stage_policy("S3", None)
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
