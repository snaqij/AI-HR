"""Role config cache.

LRU cache with TTL expiry for role configuration objects.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry."""
    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0


class ConfigCache:
    """Config cache (LRU + TTL)."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        """
        Initialize the cache.
        
        Args:
            max_size: Maximum number of cache entries
            ttl_seconds: Cache expiry time in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = RLock()
        
        # Statistics
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
        Get a cached value.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value, or None if not found or expired
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
            
            # Check if expired
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
            
            # Update access info
            entry.last_accessed = time.time()
            entry.access_count += 1
            
            # Move to end (LRU)
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
        Set a cached value.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            now = time.time()
            
            # If already exists, update
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.created_at = now
                entry.last_accessed = now
                self._cache.move_to_end(key)
            else:
                # Evict if at capacity
                if len(self._cache) >= self.max_size:
                    self._evict_oldest()
                
                # Add new entry
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
        Invalidate a cache entry.
        
        Args:
            key: Cache key
        
        Returns:
            True if the entry was removed, False otherwise
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
        """Clear all cache entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(
                "config.cache.cleared",
                extra={"cleared_count": count}
            )
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Statistics dict
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
        """Check whether a cache entry has expired."""
        age = time.time() - entry.created_at
        return age > self.ttl_seconds
    
    def _evict_oldest(self):
        """Evict the oldest cache entry (LRU)."""
        if not self._cache:
            return
        
        # The first element of OrderedDict is the oldest
        oldest_key = next(iter(self._cache))
        del self._cache[oldest_key]
        self._stats["evictions"] += 1
        
        logger.debug(
            "config.cache.evicted",
            extra={"key": oldest_key}
        )
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of entries removed
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
