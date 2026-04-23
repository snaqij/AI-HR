"""
岗位配置缓存

实现LRU缓存和TTL过期控制，提升配置加载性能。
"""

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Dict, Optional, Any

from .exceptions import CacheError

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0


class ConfigCache:
    """配置缓存（LRU + TTL）"""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = RLock()
        
        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "sets": 0,
            "invalidations": 0
        }
        
        logger.info(
            "config.cache.initialized",
            extra={
                "max_size": max_size,
                "ttl_seconds": ttl_seconds
            }
        )
    
    def get(self, key: str) -> Optional[Dict]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                logger.debug(
                    "config.cache.miss",
                    extra={"key": key}
                )
                return None
            
            # 检查是否过期
            if self._is_expired(entry):
                self._stats["expirations"] += 1
                del self._cache[key]
                logger.debug(
                    "config.cache.expired",
                    extra={
                        "key": key,
                        "age_seconds": time.time() - entry.created_at
                    }
                )
                return None
            
            # 更新访问信息
            entry.last_accessed = time.time()
            entry.access_count += 1
            
            # 移到末尾（LRU）
            self._cache.move_to_end(key)
            
            self._stats["hits"] += 1
            logger.debug(
                "config.cache.hit",
                extra={
                    "key": key,
                    "access_count": entry.access_count
                }
            )
            
            return entry.value
    
    def set(self, key: str, value: Dict):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            now = time.time()
            
            # 如果已存在，更新
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.created_at = now
                entry.last_accessed = now
                self._cache.move_to_end(key)
            else:
                # 检查是否需要驱逐
                if len(self._cache) >= self.max_size:
                    self._evict_oldest()
                
                # 添加新条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=now,
                    last_accessed=now,
                    access_count=0
                )
                self._cache[key] = entry
            
            self._stats["sets"] += 1
            logger.debug(
                "config.cache.set",
                extra={
                    "key": key,
                    "cache_size": len(self._cache)
                }
            )
    
    def invalidate(self, key: str) -> bool:
        """
        使缓存失效
        
        Args:
            key: 缓存键
        
        Returns:
            是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["invalidations"] += 1
                logger.info(
                    "config.cache.invalidated",
                    extra={"key": key}
                )
                return True
            return False
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(
                "config.cache.cleared",
                extra={"cleared_count": count}
            )
    
    def get_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests
                if total_requests > 0
                else 0.0
            )
            
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": hit_rate,
                "total_requests": total_requests
            }
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查缓存条目是否过期"""
        age = time.time() - entry.created_at
        return age > self.ttl_seconds
    
    def _evict_oldest(self):
        """驱逐最旧的缓存条目（LRU）"""
        if not self._cache:
            return
        
        # OrderedDict的第一个元素是最旧的
        oldest_key = next(iter(self._cache))
        del self._cache[oldest_key]
        self._stats["evictions"] += 1
        
        logger.debug(
            "config.cache.evicted",
            extra={"key": oldest_key}
        )
    
    def cleanup_expired(self) -> int:
        """
        清理所有过期的缓存条目
        
        Returns:
            清理的条目数
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if self._is_expired(entry)
            ]
            
            for key in expired_keys:
                del self._cache[key]
                self._stats["expirations"] += 1
            
            if expired_keys:
                logger.info(
                    "config.cache.cleanup",
                    extra={"expired_count": len(expired_keys)}
                )
            
            return len(expired_keys)
