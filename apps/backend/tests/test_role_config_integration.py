"""
Integration tests: Role config and interview flow integration

Test how role configs affect interview flow policies.
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
    """Test integration of role config with interview flow"""
    
    def test_session_role_config_storage(self):
        """Test session-level role config storage and retrieval"""
        session_id = "test_session_123"
        role_config = {
            "role": {"id": "backend_engineer"},
            "followup_strategy": {"max_per_question": 5}
        }
        
        # Store config
        set_role_config_for_session(session_id, role_config)
        
        # Retrieve config
        retrieved = get_role_config_for_session(session_id)
        assert retrieved is not None
        assert retrieved["role"]["id"] == "backend_engineer"
        assert retrieved["followup_strategy"]["max_per_question"] == 5
        
        # Clear config
        clear_role_config_for_session(session_id)
        assert get_role_config_for_session(session_id) is None
    
    def test_stage_policy_without_role_config(self):
        """Test using default policy when no role config exists"""
        session_id = "test_session_no_config"
        
        # Get S3 stage policy (without role config)
        policy = get_stage_policy("S3", session_id)
        
        # Should return default policy
        assert policy.code == "S3"
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups
    
    def test_stage_policy_with_role_config_override(self):
        """Test role config overriding stage policy"""
        session_id = "test_session_with_config"
        role_config = {
            "role": {"id": "backend_engineer"},
            "followup_strategy": {"max_per_question": 5}
        }
        
        # Store config
        set_role_config_for_session(session_id, role_config)
        
        # Get S3 stage policy (with role config)
        policy = get_stage_policy("S3", session_id)
        
        # max_followups should be overridden to 5
        assert policy.code == "S3"
        assert policy.max_followups == 5
        
        # Clear config
        clear_role_config_for_session(session_id)
    
    def test_resolve_followup_limit_priority(self):
        """Test priority order of followup limits"""
        session_id = "test_session_priority"
        role_config = {
            "followup_strategy": {"max_per_question": 5}
        }
        set_role_config_for_session(session_id, role_config)
        
        # 1. Question-specific limit (highest priority)
        question = {"max_followups": 2}
        limit = resolve_followup_limit(
            stage_code="S3",
            question=question,
            session_id=session_id
        )
        assert limit == 2
        
        # 2. Explicit default value
        limit = resolve_followup_limit(
            stage_code="S3",
            default=3,
            session_id=session_id
        )
        assert limit == 3
        
        # 3. Role config override
        limit = resolve_followup_limit(
            stage_code="S3",
            session_id=session_id
        )
        assert limit == 5
        
        # 4. Stage policy limit (lowest priority)
        clear_role_config_for_session(session_id)
        limit = resolve_followup_limit(
            stage_code="S3",
            session_id=session_id
        )
        assert limit == STAGE_POLICIES["S3"].max_followups
    
    def test_load_backend_config_and_apply(self):
        """Test loading backend engineer config and applying to session"""
        loader = RoleConfigLoader()
        
        # Load backend engineer config
        backend_config = loader.load_config("backend_engineer")
        assert backend_config is not None
        assert backend_config["role"]["id"] == "backend_engineer"
        
        # Apply to session
        session_id = "test_backend_session"
        set_role_config_for_session(session_id, backend_config)
        
        # Verify config is effective
        policy = get_stage_policy("S3", session_id)
        expected_max = backend_config["followup_strategy"]["max_per_question"]
        assert policy.max_followups == expected_max
        
        # Clear
        clear_role_config_for_session(session_id)
    
    def test_multiple_sessions_isolation(self):
        """Test config isolation between multiple sessions"""
        session1 = "session_1"
        session2 = "session_2"
        
        config1 = {"followup_strategy": {"max_per_question": 3}}
        config2 = {"followup_strategy": {"max_per_question": 5}}
        
        set_role_config_for_session(session1, config1)
        set_role_config_for_session(session2, config2)
        
        # Verify isolation
        policy1 = get_stage_policy("S3", session1)
        policy2 = get_stage_policy("S3", session2)
        
        assert policy1.max_followups == 3
        assert policy2.max_followups == 5
        
        # Clear
        clear_role_config_for_session(session1)
        clear_role_config_for_session(session2)
    
    def test_invalid_role_config_graceful_fallback(self):
        """Test graceful fallback when config is invalid"""
        session_id = "test_invalid_config"
        
        # Set invalid config (missing followup_strategy)
        invalid_config = {"role": {"id": "unknown"}}
        set_role_config_for_session(session_id, invalid_config)
        
        # Should fallback to default policy
        policy = get_stage_policy("S3", session_id)
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups
        
        clear_role_config_for_session(session_id)
    
    def test_empty_session_id_handling(self):
        """Test handling of empty session_id"""
        # Empty session_id should not crash
        set_role_config_for_session("", {"test": "config"})
        set_role_config_for_session(None, {"test": "config"})
        
        assert get_role_config_for_session("") is None
        assert get_role_config_for_session(None) is None
        
        # Getting policy without session_id should return default policy
        policy = get_stage_policy("S3", None)
        assert policy.max_followups == STAGE_POLICIES["S3"].max_followups


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
