# 岗位配置快速开始指南

## 🚀 5分钟快速上手

### 1. 验证系统是否就绪

```bash
cd AI-HR
python verify_role_config.py
```

如果看到 `✓ 所有测试通过！岗位驱动的面试流程已就绪。`，说明系统已经准备好了。

### 2. 创建面试（自动识别岗位）

```python
# 系统会自动根据job_title、jd、skills识别岗位
session = ai_interview_service.create_session(
    candidate_id="candidate_123",
    job_id="job_456"
)

# 查看识别的岗位
print(f"识别的岗位: {session['payload']['role']['display_name']['zh']}")
print(f"识别来源: {session['payload']['role']['source']}")
print(f"匹配分数: {session['payload']['role']['score']}")
```

### 3. 创建面试（手动指定岗位）

```python
# 明确指定岗位ID
session = ai_interview_service.create_session(
    candidate_id="candidate_123",
    job_id="job_456",
    explicit_role_id="backend_engineer"  # 手动指定后端工程师
)
```

### 4. 生成题目（基于岗位配置）

```python
# 系统会自动使用岗位配置生成针对性题目
result = ai_interview_service.generate_question_set(
    session_id=session["id"]
)

print(f"生成题目数量: {result.question_count}")
print(f"题目来源: {result.source}")
```

## 📋 支持的岗位列表

| 岗位ID | 中文名称 | 英文名称 | 配置文件 |
|--------|---------|---------|---------|
| `backend_engineer` | 后端工程师 | Backend Engineer | `tech/backend.yaml` |
| `frontend_engineer` | 前端工程师 | Frontend Engineer | `tech/frontend.yaml` |
| `fullstack_engineer` | 全栈工程师 | Fullstack Engineer | `tech/fullstack.yaml` |
| `product_manager` | 产品经理 | Product Manager | `product/product_manager.yaml` |
| `ui_designer` | UI设计师 | UI Designer | `design/ui_designer.yaml` |

## 🔍 岗位识别规则

### 后端工程师
- **关键词**: 后端, backend, 服务端, server, api
- **技能**: java, python, go, spring, django, mysql, redis

### 前端工程师
- **关键词**: 前端, frontend, web, h5, 移动端
- **技能**: javascript, typescript, react, vue, angular, webpack

### 全栈工程师
- **关键词**: 全栈, fullstack, full stack, 前后端
- **技能**: javascript, typescript, react, vue, node, express

### 产品经理
- **关键词**: 产品经理, product manager, pm, 产品
- **技能**: 需求分析, 产品设计, 用户研究, axure, figma

### UI设计师
- **关键词**: ui设计, ui designer, 界面设计, 视觉设计
- **技能**: figma, sketch, photoshop, illustrator

## 🎯 岗位配置的影响

### 1. 题目生成
- 注入岗位特定的上下文到LLM prompt
- 调整题目来源分布（简历/JD/模板）
- 设置锚点项目要求

### 2. 追问策略
- 岗位特定的追问次数限制
- 岗位特定的证据阈值
- 岗位特定的追问优先级

### 3. 阶段权重
- 不同岗位的阶段权重不同
- 技术岗位更重视深度追问（S3/S4）
- 产品岗位更重视经验验证（S2/S5）

### 4. 能力评估
- 通用能力（所有岗位共有）
- 岗位特定能力（如技术深度、产品sense）
- 能力权重和证据类型

## 🛠️ 添加新岗位配置

### 步骤1: 创建配置文件

```bash
# 在对应目录下创建YAML文件
touch ai_hr/role_configs/tech/mobile.yaml
```

### 步骤2: 编写配置

```yaml
version: "1.0"
extends: "_base"

role:
  id: "mobile_engineer"
  family: "engineering"
  display_name:
    zh: "移动端工程师"
    en: "Mobile Engineer"
  
  match_rules:
    keywords:
      - "移动端"
      - "mobile"
      - "ios"
      - "android"
    skills:
      - "swift"
      - "kotlin"
      - "flutter"
      - "react native"

# 岗位特定能力
role_competencies:
  mobile_development:
    weight: 0.35
    description: "移动端开发能力"
    evidence_types:
      - "native_development"
      - "cross_platform"
      - "performance_optimization"

# ... 其他配置
```

### 步骤3: 验证配置

```bash
python verify_role_config.py
```

## 🔧 调试技巧

### 1. 查看岗位识别日志

```python
import logging
logging.basicConfig(level=logging.INFO)

# 会输出类似：
# INFO:ai_hr.services.role_strategy.role_profiler:role.identify.matched 
#   role_id=backend_engineer score=5.0 job_title=后端工程师
```

### 2. 查看配置加载日志

```python
# 会输出类似：
# INFO:ai_hr.services.role_strategy.config_loader:config.load.success 
#   role_id=backend_engineer duration_ms=45.2 cache_hit=False
```

### 3. 手动测试岗位识别

```python
from ai_hr.services.role_strategy import RoleProfiler

profiler = RoleProfiler()
result = profiler.identify_role_profile(
    job_title="你的职位名称",
    jd="你的职位描述",
    skills=["技能1", "技能2"]
)

print(f"识别结果: {result.role_id}")
print(f"匹配分数: {result.score}")
print(f"匹配详情: {result.match_details}")
```

### 4. 手动测试能力映射

```python
from ai_hr.services.role_strategy import RoleConfigLoader, CompetencyMapper

loader = RoleConfigLoader()
mapper = CompetencyMapper()

config = loader.load_config("backend_engineer")
model = mapper.build_competency_model(config)

print(f"通用能力: {len(model.universal_competencies)}")
print(f"岗位能力: {len(model.role_competencies)}")
print(f"总权重: {model.total_weight}")

for comp in model.role_competencies:
    print(f"- {comp.description}: {comp.weight:.0%}")
```

## 📚 更多资源

- 完整实施总结: `ROLE_CONFIG_IMPLEMENTATION_SUMMARY.md`
- 配置规范: `ai_hr/role_configs/README.md`
- Schema定义: `ai_hr/role_configs/schema.json`
- 设计文档: `.kiro/specs/role-config-implementation/design.md`

## ❓ 常见问题

### Q1: 如何强制使用特定岗位？
A: 使用 `explicit_role_id` 参数明确指定岗位ID。

### Q2: 岗位识别不准确怎么办？
A: 可以调整配置文件中的 `match_rules`，增加更多关键词和技能。

### Q3: 如何查看当前会话使用的岗位？
A: 从 `session["payload"]["role"]` 中获取岗位信息。

### Q4: 配置修改后需要重启服务吗？
A: 目前需要重启。后续可以实现热加载功能。

### Q5: 如何回退到基础配置？
A: 系统会自动回退。也可以手动指定 `explicit_role_id="_base"`。

## 🎉 开始使用

现在你已经掌握了岗位配置系统的基本使用方法，可以开始创建岗位驱动的面试了！

如有问题，请查看完整文档或联系开发团队。
