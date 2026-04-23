"""
岗位配置监控指标

提供配置加载、缓存等操作的监控指标收集和汇总功能。
"""

import logging
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class LoadMetric:
    """配置加载指标"""
    role_id: str
    success: bool
    duration_ms: float
    cache_hit: bool
    timestamp: float
    error: str = None


class ConfigMetrics:
    """配置指标收集器"""
    
    def __init__(self, max_history: int = 1000):
        """
        初始化指标收集器
        
        Args:
            max_history: 保留的历史记录数量
        """
        self.max_history = max_history
        self._lock = RLock()
        
        # 计数器
        self._counters = {
            "load_success": 0,
            "load_failure": 0,
            "cache_hit": 0,
            "cache_miss": 0,
            "validation_success": 0,
            "validation_failure": 0
        }
        
        # 历史记录
        self._load_history: List[LoadMetric] = []
        self._duration_histogram: List[float] = []
        
        # 错误统计
        self._error_counts: Dict[str, int] = {}
    
    def record_load_success(
        self,
        role_id: str,
        duration_ms: float,
        cache_hit: bool = False
    ):
        """
        记录配置加载成功
        
        Args:
            role_id: 岗位ID
            duration_ms: 加载耗时（毫秒）
            cache_hit: 是否缓存命中
        """
        with self._lock:
            self._counters["load_success"] += 1
            if cache_hit:
                self._counters["cache_hit"] += 1
            else:
                self._counters["cache_miss"] += 1
            
            metric = LoadMetric(
                role_id=role_id,
                success=True,
                duration_ms=duration_ms,
                cache_hit=cache_hit,
                timestamp=time.time()
            )
            
            self._add_to_history(metric)
            self._duration_histogram.append(duration_ms)
            
            # 限制直方图大小
            if len(self._duration_histogram) > self.max_history:
                self._duration_histogram = self._duration_histogram[-self.max_history:]
            
            logger.debug(
                "config.metrics.load_success",
                extra={
                    "role_id": role_id,
                    "duration_ms": duration_ms,
                    "cache_hit": cache_hit
                }
            )
    
    def record_load_failure(self, role_id: str, error: str, duration_ms: float = 0):
        """
        记录配置加载失败
        
        Args:
            role_id: 岗位ID
            error: 错误信息
            duration_ms: 加载耗时（毫秒）
        """
        with self._lock:
            self._counters["load_failure"] += 1
            self._counters["cache_miss"] += 1
            
            # 统计错误类型
            error_type = error.split(":")[0] if ":" in error else error
            self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1
            
            metric = LoadMetric(
                role_id=role_id,
                success=False,
                duration_ms=duration_ms,
                cache_hit=False,
                timestamp=time.time(),
                error=error
            )
            
            self._add_to_history(metric)
            
            logger.warning(
                "config.metrics.load_failure",
                extra={
                    "role_id": role_id,
                    "error": error,
                    "duration_ms": duration_ms
                }
            )
    
    def record_validation_success(self, role_id: str):
        """记录配置验证成功"""
        with self._lock:
            self._counters["validation_success"] += 1
    
    def record_validation_failure(self, role_id: str, error_count: int):
        """记录配置验证失败"""
        with self._lock:
            self._counters["validation_failure"] += 1
            
            logger.warning(
                "config.metrics.validation_failure",
                extra={
                    "role_id": role_id,
                    "error_count": error_count
                }
            )
    
    def get_summary(self) -> Dict:
        """
        获取指标汇总
        
        Returns:
            指标汇总字典
        """
        with self._lock:
            total_loads = (
                self._counters["load_success"] + self._counters["load_failure"]
            )
            success_rate = (
                self._counters["load_success"] / total_loads
                if total_loads > 0
                else 0.0
            )
            
            total_cache_requests = (
                self._counters["cache_hit"] + self._counters["cache_miss"]
            )
            cache_hit_rate = (
                self._counters["cache_hit"] / total_cache_requests
                if total_cache_requests > 0
                else 0.0
            )
            
            # 计算耗时统计
            duration_stats = self._calculate_duration_stats()
            
            return {
                "counters": dict(self._counters),
                "success_rate": success_rate,
                "cache_hit_rate": cache_hit_rate,
                "total_loads": total_loads,
                "duration_stats": duration_stats,
                "error_counts": dict(self._error_counts),
                "history_size": len(self._load_history)
            }
    
    def get_recent_failures(self, limit: int = 10) -> List[LoadMetric]:
        """
        获取最近的失败记录
        
        Args:
            limit: 返回的记录数量
        
        Returns:
            失败记录列表
        """
        with self._lock:
            failures = [m for m in self._load_history if not m.success]
            return failures[-limit:]
    
    def reset(self):
        """重置所有指标"""
        with self._lock:
            self._counters = {k: 0 for k in self._counters}
            self._load_history.clear()
            self._duration_histogram.clear()
            self._error_counts.clear()
            
            logger.info("config.metrics.reset")
    
    def _add_to_history(self, metric: LoadMetric):
        """添加到历史记录"""
        self._load_history.append(metric)
        
        # 限制历史记录大小
        if len(self._load_history) > self.max_history:
            self._load_history = self._load_history[-self.max_history:]
    
    def _calculate_duration_stats(self) -> Dict:
        """计算耗时统计"""
        if not self._duration_histogram:
            return {
                "min": 0,
                "max": 0,
                "avg": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0
            }
        
        sorted_durations = sorted(self._duration_histogram)
        n = len(sorted_durations)
        
        return {
            "min": sorted_durations[0],
            "max": sorted_durations[-1],
            "avg": sum(sorted_durations) / n,
            "p50": sorted_durations[int(n * 0.5)],
            "p95": sorted_durations[int(n * 0.95)],
            "p99": sorted_durations[int(n * 0.99)]
        }


# 全局指标实例
_global_metrics = ConfigMetrics()


def get_metrics() -> ConfigMetrics:
    """获取全局指标实例"""
    return _global_metrics
