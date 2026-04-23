# 岗位配置化改造设计文档

## 1. 架构设计

### 1.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    应用层 (Application Layer)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  AIInterviewService                                   │  │
│  │  - generate_question_set()                           │  │
│  │  - _build_questions_with_llm()                       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  岗位策略层 (Role Strategy Layer)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ RoleProfiler │  │ ConfigLoader │  │ ConfigCache  │    │
│  │ 岗位识别器    │  │ 配置加载器    │  │ 配置缓存     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  配置层 (Configuration Layer)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  YAML配置文件                                         │  │
│  │  - _base.yaml (基础配置)                             │  │
│  │  - tech/*.yaml (技术岗位)                            │  │
│  │  - product/*.yaml (产品岗位)                         │  │
│  │  - design/*.yaml (设计岗位)                          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心组件

#### 1.2.1 RoleConfigLoader (配置加载器)
**职责**：
- 加载YAML配置文件
- 处理配置继承（extends）
- 验证配置有效性
- 管理配置缓存

**接口**：
```python
class RoleConfigLoader:
    def load_config(role_id: str) -> Optional[Dict]
    def load_base_config() -> Dict
    def load_all_configs() -> Dict[str, Dict]
    def reload_config(role_id: str) -> Dict
```

#### 1.2.2 RoleConfigValidator (配置验证器)
**职责**：
- JSON Schema验证
- 业务规则验证
- 权重总和验证
- 引用完整性验证

**接口**：
```python
class RoleConfigValidator:
    def validate(config: Dict) -> Tuple[bool, List[str]]
    def validate_file(file_path: str) -> Tuple[bool, List[str]]
```

#### 1.2.3 ConfigCache (配置缓存)
**职责**：
- LRU缓存管理
- TTL过期控制
- 缓存统计

**接口**：
```python
class ConfigCache:
    def get(key: str) -> Optional[Dict]
    def set(key: str, config: Dict)
    def invalidate(key: str)
    def clear()
```

#### 1.2.4 RoleProfiler (岗位识别器)
**职责**：
- 基于关键词识别岗位
- 基于技能标签识别岗位
- 计算匹配分数
- 回退到基础配置

**接口**：
```python
class RoleProfiler:
    def identify_role(
        job_title: str,
        jd: str,
        skills: List[str],
        explicit_role_id: Optional[str]
    ) -> RoleConfig
```

## 2. 数据模型设计

### 2.1 配置文件结构

```yaml
# 配置版本
version: "1.0"

# 继承基础配置
extends: "_base"

# 岗位信息
role:
  id: "backend_engineer"
  family: "engineering"
  display_name:
    zh: "后端工程师"
    en: "Backend Engineer"
  match_rules:
    keywords: ["后端", "backend", "java"]
    skills: ["spring", "mysql", "redis"]

# 通用能力
universal_competencies:
  ownership:
    weight: 0.15
    description: "主人翁意识"
    evidence_types: ["initiative", "responsibility"]

# 岗位特定能力
role_competencies:
  technical_depth:
    weight: 0.25
    description: "技术深度"
    evidence_types: ["real_usage", "technical_detail"]

# 阶段权重
stage_weights:
  S3: 0.35
  S4: 0.35

# 题目生成策略
question_generation:
  distribution:
    from_resume: 0.60
    from_jd: 0.30
    from_template: 0.10
  anchor_project:
    required: true
    min_duration_months: 3

# 追问策略
followup_strategy:
  max_per_question: 3
  evidence_threshold: 0.7
  priority: ["technical_detail", "architecture"]

# Prompt增强
prompt_enhancements:
  role_context: "候选人应聘后端工程师..."
  question_focus: "题目应围绕项目经历..."
  followup_focus: "追问应针对技术细节..."
```

### 2.2 Python数据模型

```python
@dataclass
class RoleConfig:
    """岗位配置"""
    version: str
    role_id: str
    role_family: str
    display_name: Dict[str, str]
    match_rules: Dict[str, List[str]]
    universal_competencies: Dict[str, CompetencyConfig]
    role_competencies: Dict[str, CompetencyConfig]
    stage_weights: Dict[str, float]
    question_generation: QuestionGenerationConfig
    followup_strategy: FollowupStrategyConfig
    prompt_enhancements: PromptEnhancementsConfig

@dataclass
class CompetencyConfig:
    """能力配置"""
    weight: float
    description: str
    evidence_types: List[str]

@dataclass
class QuestionGenerationConfig:
    """题目生成配置"""
    distribution: Dict[str, float]
    anchor_project: AnchorProjectConfig

@dataclass
class FollowupStrategyConfig:
    """追问策略配置"""
    max_per_question: int
    evidence_threshold: float
    priority: List[str]
```

## 3. 配置加载流程

### 3.1 加载流程图

```
开始
  ↓
检查缓存
  ↓
缓存命中? ──是→ 返回缓存配置
  ↓ 否
查找配置文件
  ↓
文件存在? ──否→ 返回None
  ↓ 是
加载YAML文件
  ↓
处理extends继承
  ↓
验证配置
  ↓
验证通过? ──否→ 抛出异常
  ↓ 是
写入缓存
  ↓
返回配置
```

### 3.2 配置继承机制

```python
# backend.yaml
extends: "_base"
role_competencies:
  technical_depth:
    weight: 0.25

# 加载后合并结果
{
  # 从_base.yaml继承
  "universal_competencies": {...},
  "default_stage_weights": {...},
  
  # backend.yaml覆盖
  "role_competencies": {
    "technical_depth": {"weight": 0.25}
  }
}
```

## 4. 岗位识别流程

### 4.1 识别流程图

```
开始
  ↓
明确指定role_id? ──是→ 直接加载配置
  ↓ 否
提取job_title、jd、skills
  ↓
遍历所有配置的match_rules
  ↓
计算匹配分数
  ↓
找到最佳匹配? ──是→ 加载对应配置
  ↓ 否
加载基础配置
  ↓
返回配置
```

### 4.2 匹配分数计算

```python
def calculate_match_score(
    text: str,
    keywords: List[str],
    skills: List[str]
) -> float:
    """
    计算匹配分数
    
    分数 = 关键词匹配数 × 2 + 技能匹配数 × 1
    """
    keyword_score = sum(1 for kw in keywords if kw.lower() in text.lower())
    skill_score = sum(1 for sk in skills if sk.lower() in text.lower())
    
    return keyword_score * 2 + skill_score
```

## 5. 集成点设计

### 5.1 ai_interviews.py集成

```python
class AIInterviewQuestionGenerationMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 新增：初始化岗位识别器
        self.role_profiler = RoleProfiler()
    
    def generate_question_set(
        self,
        session_id: str,
        explicit_role_id: str = None  # 新增参数
    ):
        # 1. 识别岗位
        role_config = self.role_profiler.identify_role(
            job_title=job.title,
            jd=job.requirements,
            skills=candidate.skills,
            explicit_role_id=explicit_role_id
        )
        
        # 2. 存储岗位信息到session
        self._session_repository.update_status(
            session_id,
            payload_patch={
                "role_id": role_config.role_id,
                "role_family": role_config.role_family
            }
        )
        
        # 3. 传递配置到题目生成
        questions = self._build_questions_with_llm(
            ...,
            role_config=role_config  # 新增参数
        )
```

### 5.2 flow_policy.py集成

```python
# 全局配置缓存
_ROLE_CONFIG_CACHE: Dict[str, Dict] = {}

def get_stage_policy(
    stage_code: str,
    session_id: str = None  # 新增参数
) -> StagePolicy:
    """获取阶段策略（支持岗位配置覆盖）"""
    base_policy = STAGE_POLICIES[stage_code]
    
    if not session_id:
        return base_policy
    
    # 获取岗位配置
    role_config = _ROLE_CONFIG_CACHE.get(session_id)
    if not role_config:
        return base_policy
    
    # 应用覆盖
    stage_overrides = role_config.get("stage_overrides", {}).get(stage_code, {})
    if stage_overrides:
        return apply_overrides(base_policy, stage_overrides)
    
    return base_policy
```

## 6. 监控和日志设计

### 6.1 日志级别

- **DEBUG**: 配置加载详情、缓存命中/未命中
- **INFO**: 配置加载成功、岗位识别结果
- **WARNING**: 配置不存在、识别失败回退
- **ERROR**: 配置加载失败、验证失败

### 6.2 监控指标

```python
class ConfigMetrics:
    """配置加载指标"""
    
    # 计数器
    load_success_count: int
    load_failure_count: int
    cache_hit_count: int
    cache_miss_count: int
    
    # 直方图
    load_duration_histogram: List[float]
    
    # 方法
    def record_load_success(role_id: str, duration: float)
    def record_load_failure(role_id: str, error: str)
    def record_cache_hit(role_id: str)
    def record_cache_miss(role_id: str)
    def get_summary() -> Dict
```

### 6.3 日志格式

```python
logger.info(
    "config.load.success",
    extra={
        "role_id": "backend_engineer",
        "duration_ms": 45.2,
        "cache_hit": False,
        "file_path": "role_configs/tech/backend.yaml"
    }
)
```

## 7. 错误处理设计

### 7.1 异常层次

```python
class RoleConfigError(Exception):
    """岗位配置基础异常"""
    pass

class ConfigNotFoundError(RoleConfigError):
    """配置不存在"""
    pass

class ConfigLoadError(RoleConfigError):
    """配置加载失败"""
    pass

class ConfigValidationError(RoleConfigError):
    """配置验证失败"""
    pass
```

### 7.2 错误处理策略

| 错误类型 | 处理策略 | 影响范围 |
|---------|---------|---------|
| 配置不存在 | 回退到基础配置 | 单个面试 |
| 配置加载失败 | 回退到基础配置 | 单个面试 |
| 配置验证失败 | 抛出异常，记录日志 | 单个面试 |
| 缓存失败 | 降级到直接加载 | 性能影响 |

## 8. 性能优化设计

### 8.1 缓存策略

- **L1缓存**: 进程内存缓存（LRU + TTL）
- **缓存大小**: 100个配置
- **TTL**: 3600秒（1小时）
- **预热**: 启动时加载常用配置

### 8.2 懒加载

- 配置文件按需加载
- 不在启动时加载所有配置
- 减少启动时间

### 8.3 热加载（可选）

- 后台线程定期检查文件变更
- 检测到变更时清除缓存
- 下次访问时重新加载

## 9. 测试策略

### 9.1 单元测试

- 配置加载器测试
- 配置验证器测试
- 岗位识别器测试
- 缓存测试

### 9.2 集成测试

- 端到端面试流程测试
- 配置继承测试
- 错误处理测试

### 9.3 性能测试

- 配置加载性能测试
- 缓存命中率测试
- 并发加载测试

## 10. 部署和运维

### 10.1 配置文件管理

- 配置文件纳入Git版本控制
- 配置变更需要Code Review
- 提供配置验证脚本

### 10.2 监控告警

- 配置加载失败率告警
- 缓存命中率告警
- 配置加载耗时告警

### 10.3 回滚机制

- Git回滚配置文件
- 清除缓存强制重新加载
- 提供配置版本管理
