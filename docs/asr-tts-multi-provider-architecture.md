# AI-HR ASR/TTS 多 Provider 解耦技术设计文档

## 1. 文档目的
本文用于指导 AI-HR 将语音能力从“固定厂商硬编码”升级为“可配置、可扩展、可观测、可治理”的企业级多 Provider 平台，覆盖国内外主流 ASR/TTS 服务。

## 2. 当前现状与核心问题
当前语音入口在 `apps/backend/ai_hr/services/speech/factory.py`，虽已有抽象接口，但仍存在以下问题：

1. Provider 选择逻辑为硬编码 `if/else`，新增厂商改动面大。
2. TEN 运行时在 `apps/backend/ai_hr/services/ten_runtime.py` 中写死节点与属性映射。
3. TEN 扩展通过 `sys.path` 直接引用 backend provider，模块边界不清晰。
4. 健康检查 `apps/backend/ai_hr/services/providers/health.py` 与真实凭据模型不完全一致。
5. 用户配置与系统内部调优参数混杂，开源接入门槛高。

## 3. 改造目标
1. 用户仅需完成“选择 Provider + 填写凭据”。
2. 新增 Provider 不修改业务主流程。
3. 同时支持 Backend 直连与 TEN 两套运行时。
4. 支持主备、熔断、降级、区域路由。
5. 满足企业级安全、观测、运维治理要求。

## 4. 非目标
1. 本阶段不重构面试业务流程与评估逻辑。
2. 本阶段不做全平台服务网格改造。
3. 本阶段不跨域改造与语音无关模块。

## 5. 目标架构

### 5.1 分层模型
1. Capability Layer：定义能力维度，如 `asr_realtime`、`asr_batch`、`tts_realtime`、`tts_batch`。
2. Registry Layer：管理 Provider 元数据、能力声明、配置 schema。
3. Binding Layer：按环境/租户/场景绑定主备 Provider。
4. Routing Layer：按策略路由并负责失败切换。
5. Runtime Adapter Layer：分别适配 Backend 与 TEN。
6. Observability Layer：统一日志、指标、健康、成本。

### 5.2 建议代码结构
新增或改造以下文件：

1. `apps/backend/ai_hr/services/speech/contracts.py`
2. `apps/backend/ai_hr/services/speech/registry.py`
3. `apps/backend/ai_hr/services/speech/bindings.py`
4. `apps/backend/ai_hr/services/speech/router.py`
5. `apps/backend/ai_hr/services/speech/provider_loader.py`
6. `apps/backend/ai_hr/services/speech/factory.py`（重构）
7. `apps/backend/ai_hr/services/ten_runtime_adapter.py`
8. `apps/backend/ai_hr/services/ten_runtime.py`（去硬编码）
9. `apps/backend/ai_hr/services/providers/health.py`（按 schema 校验）
10. `docs/provider-integration.md`
11. `docs/provider-operations.md`

## 6. 数据模型设计
新增四张表：

1. `provider_catalog`
2. `provider_bindings`
3. `provider_credentials_ref`
4. `provider_health_snapshots`

### 6.1 SQL 草案
```sql
CREATE TABLE provider_catalog (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  provider_key VARCHAR(64) NOT NULL,
  capability VARCHAR(32) NOT NULL,
  runtime_support VARCHAR(16) NOT NULL,
  regions_json JSON NOT NULL,
  config_schema_json JSON NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_provider_capability (provider_key, capability)
);

CREATE TABLE provider_credentials_ref (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  credential_key VARCHAR(128) NOT NULL,
  secret_backend VARCHAR(32) NOT NULL,
  meta_json JSON NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_credential_key (credential_key)
);

CREATE TABLE provider_bindings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  scope_type VARCHAR(16) NOT NULL,
  scope_id VARCHAR(64) NOT NULL,
  capability VARCHAR(32) NOT NULL,
  primary_provider_key VARCHAR(64) NOT NULL,
  secondary_provider_key VARCHAR(64) NULL,
  routing_policy_json JSON NOT NULL,
  credential_ref_primary BIGINT NOT NULL,
  credential_ref_secondary BIGINT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE provider_health_snapshots (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  provider_key VARCHAR(64) NOT NULL,
  capability VARCHAR(32) NOT NULL,
  region VARCHAR(32) NOT NULL,
  health_score DECIMAL(5,2) NOT NULL,
  p95_ms INT NOT NULL,
  error_rate DECIMAL(6,4) NOT NULL,
  sample_count INT NOT NULL,
  snapshot_at DATETIME NOT NULL
);
```

## 7. 核心接口定义

### 7.1 Provider 描述契约
`contracts.py` 中定义：

```python
@dataclass
class ProviderDescriptor:
    provider_key: str
    capability: str
    runtime_support: str
    required_fields: list[str]
    optional_fields: list[str]
    regions: list[str]
```

### 7.2 Registry 接口
`registry.py`：

```python
class ProviderRegistry:
    def register(self, descriptor: ProviderDescriptor) -> None: ...
    def list(self, capability: str) -> list[ProviderDescriptor]: ...
    def get(self, provider_key: str, capability: str) -> ProviderDescriptor: ...
```

### 7.3 Binding 解析接口
`bindings.py`：

```python
class BindingResolver:
    def resolve(self, scope_type: str, scope_id: str, capability: str) -> BindingResult: ...
```

### 7.4 路由接口
`router.py`：

```python
class SpeechRouter:
    def select(self, binding: BindingResult, context: RouteContext) -> SelectedProvider: ...
    def on_failure(self, selected: SelectedProvider, error: Exception) -> SelectedProvider: ...
```

## 8. 主流 Provider 覆盖范围

### 8.1 国内
1. ASR：阿里云 NLS、腾讯云 ASR、百度 ASR、讯飞 ASR、火山 ASR。
2. TTS：阿里云 TTS、腾讯云 TTS、百度 TTS、讯飞 TTS、火山 TTS。

### 8.2 国际
1. ASR：Google STT、Azure Speech、AWS Transcribe、Deepgram、OpenAI。
2. TTS：Azure Neural TTS、Google Cloud TTS、AWS Polly、ElevenLabs、OpenAI TTS。

## 9. 运行时解耦方案

### 9.1 Backend 运行时
1. 保留 `ASRProvider` / `TTSProvider` 接口。
2. 工厂由硬编码切为 `registry + router + provider_loader`。
3. 会话级 provider pinning，避免音色/识别漂移。

### 9.2 TEN 运行时
1. 新增 `ten_runtime_adapter.py`。
2. 将 TEN 节点映射改为能力占位符渲染，不再写死厂商节点名。
3. 会话启动时由 adapter 将能力绑定渲染为具体 TEN graph/property。
4. 保留一版兼容路径用于灰度窗口。

## 10. 安全与密钥管理
1. 禁止明文密钥进入仓库、静态 manifest、日志。
2. 数据库存储 `credentials_ref`，不存明文凭据。
3. 运行时从 Vault/KMS/云 Secret Manager 拉取短期凭据。
4. 具备轮换、过期、审计、告警能力。
5. 对事件与日志敏感字段统一脱敏。

## 11. 可观测与 SLO

### 11.1 指标
1. `speech_asr_p95_ms`
2. `speech_tts_first_packet_p95_ms`
3. `speech_provider_error_rate`
4. `speech_failover_count`
5. `speech_cost_per_session`

### 11.2 日志标准字段
1. `trace_id`
2. `session_id`
3. `provider_key`
4. `region`
5. `fallback_reason`
6. `latency_breakdown`

## 12. 分阶段实施步骤

### 阶段 A（第 1-2 周）：Registry + 配置标准化
1. 新建 `contracts.py`、`registry.py`。
2. 将现有 `mock/tencent/aliyun/openai` provider 注册化。
3. 重构 factory 为 loader 驱动并保留兼容逻辑。
4. 初始化 `provider_catalog` 数据。

**验收标准**
- 新增 provider 不需要修改工厂核心分支逻辑。

### 阶段 B（第 3-4 周）：Binding + Routing
1. 新增 binding 表及 repository。
2. 实现全局默认绑定解析。
3. 实现主备切换策略。
4. 在 `asr_stream`/`tts_stream` 接入路由。

**验收标准**
- 注入主 provider 故障后可自动切备。

### 阶段 C（第 5-6 周）：TEN Adapter 解耦
1. 新增 `ten_runtime_adapter.py`。
2. 从 `ten_runtime.py` 移除固定厂商节点映射。
3. 引入 TEN 能力占位模板渲染。
4. 保留旧路径一版发布周期用于回滚。

**验收标准**
- 单一 TEN 模板可通过配置切换不同 ASR/TTS。

### 阶段 D（第 7-8 周）：管理 API 与运维控制
1. 新增 API：
   - `GET /admin/providers/catalog`
   - `GET /admin/providers/bindings`
   - `PUT /admin/providers/bindings`
   - `POST /admin/providers/validate`
   - `POST /admin/providers/failover/drill`
2. 健康检查改为 schema 感知。
3. 输出可操作的缺失配置提示。

**验收标准**
- 通过管理接口可安全切换 provider 绑定。

### 阶段 E（第 9-10 周）：可靠性与成本治理
1. 增加区域路由。
2. 增加延迟/成本策略约束。
3. provider 级重试、熔断、回退打通。
4. 接入会话级成本统计。

**验收标准**
- 路由策略可稳定约束延迟和成本。

### 阶段 F（第 11-12 周）：安全加固与灰度上线
1. 全面接入 Secret Backend。
2. 建立灰度发布和回滚机制。
3. 完成值班 runbook 与故障演练。

**验收标准**
- 无明文密钥暴露，具备生产可运维能力。

## 13. 用户配置体验改造
1. 保持最小化 `infra/env/.env.example`。
2. 增加 profile 模板：
   - `profile.cn-realtime.env`
   - `profile.global-realtime.env`
   - `profile.mock-local.env`
3. 新增工具：

```bash
uv run python -m ai_hr.tools.validate_config
uv run python -m ai_hr.tools.provider_probe --capability asr_realtime
```

4. 启动前打印缺失项与配置链接。

## 14. 测试与质量门禁

### 14.1 单元测试
1. registry 注册/查询。
2. binding 优先级解析。
3. 路由主备与失败切换。
4. provider 配置 schema 校验。

### 14.2 集成测试
1. `asr_stream` 与 `tts_stream` API 链路。
2. TEN 属性渲染与节点映射。
3. health API 在各 provider 下校验准确性。

### 14.3 故障演练
1. 主 provider 超时。
2. 凭据失效。
3. 区域不可用。

### 14.4 性能压测
1. 会话并发 100/500/1000。
2. 首包时延、最终转写时延、降级率。

## 15. 风险与应对
1. 路由层引入额外时延。
- 应对：会话 pinning + 热缓存。
2. TEN 动态渲染提升排障难度。
- 应对：持久化渲染结果并绑定 trace_id。
3. 厂商错误码不统一。
- 应对：统一错误码映射层。
4. 回退导致成本上升。
- 应对：预算告警 + 成本上限策略。

## 16. 上线验收标准
1. 新增 1 家 ASR/TTS 厂商无需改业务主流程。
2. 单厂商故障自动切备，连续性 > 99%。
3. 实时会话 P95 延迟劣化不超过 10%。
4. 密钥零明文入仓、零明文日志。
5. 国内/国际 profile 可独立一键部署。

## 17. 立即执行的首批 PR（Phase A）
1. 引入 speech contracts 与 provider registry。
2. 重构 factory 为 registry 驱动。
3. 增加 provider 配置校验工具。
4. 增加 `provider_catalog` 初始化迁移脚本。
