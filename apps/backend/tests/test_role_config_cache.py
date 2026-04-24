"""Unit tests for ConfigCache."""

from __future__ import annotations

import time

import pytest

from ai_hr.services.role_strategy.config_cache import ConfigCache


class TestConfigCache:
    """配置缓存测试"""
    
    @pytest.fixture
    def cache(self):
        """创建缓存实例"""
        return ConfigCache(max_size=3, ttl_seconds=1)
    
    @pytest.fixture
    def sample_config(self):
        """示例配置"""
        return {
            "role": {"id": "test_role"},
            "version": "1.0"
        }
    
    def test_set_and_get(self, cache, sample_config):
        """测试设置和获取"""
        cache.set("test_role", sample_config)
        result = cache.get("test_role")
        assert result == sample_config
    
    def test_get_nonexistent(self, cache):
        """测试获取不存在的键"""
        result = cache.get("nonexistent")
        assert result is None
    
    def test_ttl_expiration(self, cache, sample_config):
        """测试TTL过期"""
        cache.set("test_role", sample_config)
        
        # Immediate get should succeed.
        assert cache.get("test_role") is not None
        
        # Wait for expiration.
        time.sleep(1.1)
        
        # After expiration it should return None.
        assert cache.get("test_role") is None
    
    def test_lru_eviction(self, cache, sample_config):
        """测试LRU驱逐"""
        # Fill cache to capacity.
        cache.set("role1", {"id": "role1"})
        cache.set("role2", {"id": "role2"})
        cache.set("role3", {"id": "role3"})
        
        # Adding role4 should evict the oldest (role1).
        cache.set("role4", {"id": "role4"})
        
        assert cache.get("role1") is None
        assert cache.get("role2") is not None
        assert cache.get("role3") is not None
        assert cache.get("role4") is not None
    
    def test_lru_access_updates_order(self, cache):
        """测试访问更新LRU顺序"""
        cache.set("role1", {"id": "role1"})
        cache.set("role2", {"id": "role2"})
        cache.set("role3", {"id": "role3"})
        
        # Access role1 so it becomes most recent.
        cache.get("role1")
        
        # Adding role4 should evict role2 (oldest).
        cache.set("role4", {"id": "role4"})
        
        assert cache.get("role1") is not None
        assert cache.get("role2") is None
        assert cache.get("role3") is not None
        assert cache.get("role4") is not None
    
    def test_invalidate(self, cache, sample_config):
        """测试使缓存失效"""
        cache.set("test_role", sample_config)
        assert cache.get("test_role") is not None
        
        result = cache.invalidate("test_role")
        assert result is True
        assert cache.get("test_role") is None
        
        # Re-invalidating should return False.
        result = cache.invalidate("test_role")
        assert result is False
    
    def test_clear(self, cache):
        """测试清空缓存"""
        cache.set("role1", {"id": "role1"})
        cache.set("role2", {"id": "role2"})
        
        cache.clear()
        
        assert cache.get("role1") is None
        assert cache.get("role2") is None
    
    def test_get_stats(self, cache, sample_config):
        """测试获取统计信息"""
        cache.set("role1", sample_config)
        cache.get("role1")  # hit
        cache.get("role2")  # miss
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5
    
    def test_cleanup_expired(self, cache):
        """测试清理过期条目"""
        cache.set("role1", {"id": "role1"})
        cache.set("role2", {"id": "role2"})
        
        # Wait for expiration.
        time.sleep(1.1)
        
        # Cleanup expired entries.
        count = cache.cleanup_expired()
        
        assert count == 2
        assert cache.get("role1") is None
        assert cache.get("role2") is None
