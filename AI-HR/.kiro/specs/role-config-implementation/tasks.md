# 岗位配置化改造任务清单

## Phase 1: 基础设施搭建

### 1.1 创建目录结构
- [x] 1.1.1 创建 `ai_hr/role_configs/` 目录
- [x] 1.1.2 创建 `ai_hr/role_configs/tech/` 目录
- [x] 1.1.3 创建 `ai_hr/role_configs/product/` 目录
- [x] 1.1.4 创建 `ai_hr/role_configs/design/` 目录
- [x] 1.1.5 创建 `ai_hr/role_configs/business/` 目录
- [x] 1.1.6 创建 `ai_hr/services/role_strategy/` 目录

### 1.2 实现配置验证器
- [x] 1.2.1 创建 `schema.json` JSON Schema文件
- [x] 1.2.2 实现 `config_validator.py` 基础类
- [x] 1.2.3 实现 JSON Schema验证
- [x] 1.2.4 实现业务规则验证
- [x] 1.2.5 实现权重总和验证
- [x] 1.2.6 编写单元测试

### 1.3 实现配置缓存
- [x] 1.3.1 创建 `config_cache.py`
- [x] 1.3.2 实现 LRU缓存逻辑
- [x] 1.3.3 实现 TTL过期控制
- [x] 1.3.4 实现缓存统计
- [x] 1.3.5 编写单元测试

### 1.4 实现配置加载器
- [x] 1.4.1 创建 `config_loader.py`
- [x] 1.4.2 实现 YAML文件加载
- [x] 1.4.3 实现配置继承（extends）
- [x] 1.4.4 集成配置验证器
- [x] 1.4.5 集成配置缓存
- [ ] 1.4.6 实现热加载（可选）
- [x] 1.4.7 编写单元测试

### 1.5 实现监控指标
- [x] 1.5.1 创建 `metrics.py`
- [x] 1.5.2 实现配置加载指标
- [x] 1.5.3 实现缓存指标
- [x] 1.5.4 实现指标汇总

### 1.6 实现自定义异常
- [x] 1.6.1 创建 `exceptions.py`
- [x] 1.6.2 定义异常层次结构
- [x] 1.6.3 实现异常消息格式化

## Phase 2: 岗位识别实现

### 2.1 实现岗位识别器
- [x] 2.1.1 创建 `role_profiler.py`
- [x] 2.1.2 实现关键词匹配逻辑
- [x] 2.1.3 实现技能标签匹配逻辑
- [x] 2.1.4 实现匹配分数计算
- [x] 2.1.5 实现回退到基础配置
- [x] 2.1.6 编写单元测试

### 2.2 实现能力映射器
- [ ] 2.2.1 创建 `competency_mapper.py`
- [ ] 2.2.2 实现能力模型构建
- [ ] 2.2.3 实现能力权重计算
- [ ] 2.2.4 编写单元测试

## Phase 3: 集成改造

### 3.1 修改 ai_interviews.py
- [x] 3.1.1 在 `__init__` 中初始化 RoleProfiler
- [x] 3.1.2 修改 `generate_question_set` 添加岗位识别
- [x] 3.1.3 修改 `_generate_questions_with_fallback` 传递role_config
- [x] 3.1.4 修改 `_build_questions_with_llm` 注入岗位上下文
- [x] 3.1.5 实现 `_build_role_context` 方法
- [x] 3.1.6 更新session payload存储岗位信息

### 3.2 修改 flow_policy.py
- [x] 3.2.1 添加全局配置缓存
- [x] 3.2.2 实现 `set_role_config_for_session`
- [x] 3.2.3 实现 `get_role_config_for_session`
- [x] 3.2.4 修改 `get_stage_policy` 支持配置覆盖
- [x] 3.2.5 实现配置覆盖逻辑

### 3.3 集成测试
- [ ] 3.3.1 编写端到端面试流程测试
- [ ] 3.3.2 编写岗位识别集成测试
- [ ] 3.3.3 编写配置加载集成测试
- [ ] 3.3.4 编写错误处理测试

## Phase 4: 配置文件编写

### 4.1 编写基础配置
- [x] 4.1.1 创建 `_base.yaml`
- [x] 4.1.2 定义通用能力
- [x] 4.1.3 定义默认阶段权重
- [x] 4.1.4 定义默认追问策略
- [ ] 4.1.5 验证配置有效性

### 4.2 编写技术岗位配置
- [x] 4.2.1 创建 `tech/backend.yaml`
- [ ] 4.2.2 创建 `tech/frontend.yaml`
- [ ] 4.2.3 创建 `tech/fullstack.yaml`
- [ ] 4.2.4 创建 `tech/mobile.yaml`
- [ ] 4.2.5 创建 `tech/ai_ml.yaml`
- [ ] 4.2.6 创建 `tech/qa.yaml`
- [ ] 4.2.7 创建 `tech/sre.yaml`
- [ ] 4.2.8 验证所有配置

### 4.3 编写产品岗位配置
- [ ] 4.3.1 创建 `product/product_manager.yaml`
- [ ] 4.3.2 创建 `product/product_owner.yaml`
- [ ] 4.3.3 创建 `product/technical_pm.yaml`
- [ ] 4.3.4 验证所有配置

### 4.4 编写设计岗位配置
- [ ] 4.4.1 创建 `design/ui_designer.yaml`
- [ ] 4.4.2 创建 `design/ux_designer.yaml`
- [ ] 4.4.3 创建 `design/interaction_designer.yaml`
- [ ] 4.4.4 验证所有配置

### 4.5 编写商业岗位配置
- [ ] 4.5.1 创建 `business/sales.yaml`
- [ ] 4.5.2 创建 `business/marketing.yaml`
- [ ] 4.5.3 创建 `business/operations.yaml`
- [ ] 4.5.4 验证所有配置

## Phase 5: 测试和优化

### 5.1 单元测试
- [ ] 5.1.1 配置加载器测试覆盖率 > 80%
- [ ] 5.1.2 配置验证器测试覆盖率 > 80%
- [ ] 5.1.3 岗位识别器测试覆盖率 > 80%
- [ ] 5.1.4 配置缓存测试覆盖率 > 80%

### 5.2 性能测试
- [ ] 5.2.1 配置加载性能测试
- [ ] 5.2.2 缓存命中率测试
- [ ] 5.2.3 并发加载测试
- [ ] 5.2.4 内存使用测试

### 5.3 压力测试
- [ ] 5.3.1 高并发场景测试
- [ ] 5.3.2 大量配置加载测试
- [ ] 5.3.3 长时间运行测试

### 5.4 优化
- [ ] 5.4.1 性能瓶颈分析
- [ ] 5.4.2 代码优化
- [ ] 5.4.3 缓存策略优化
- [ ] 5.4.4 日志优化

## Phase 6: 文档和发布

### 6.1 编写配置文档
- [ ] 6.1.1 创建 `role_configs/README.md`
- [ ] 6.1.2 创建 `role_configs/CONTRIBUTING.md`
- [ ] 6.1.3 编写配置规范文档
- [ ] 6.1.4 编写配置示例
- [ ] 6.1.5 编写最佳实践文档

### 6.2 编写开发者文档
- [ ] 6.2.1 编写架构设计文档
- [ ] 6.2.2 编写API文档
- [ ] 6.2.3 编写扩展指南
- [ ] 6.2.4 编写故障排查文档

### 6.3 编写用户文档
- [ ] 6.3.1 编写快速开始指南
- [ ] 6.3.2 编写配置教程
- [ ] 6.3.3 编写FAQ文档
- [ ] 6.3.4 编写迁移指南

### 6.4 代码审查和发布
- [ ] 6.4.1 代码自审
- [ ] 6.4.2 Peer Review
- [ ] 6.4.3 代码质量检查（pylint, mypy）
- [ ] 6.4.4 准备发布说明
- [ ] 6.4.5 创建发布分支
