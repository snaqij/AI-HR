# AI-HR 已实现功能清单（仅基于代码落地）

最后更新：2026-03-21

## 更新规则（持续维护）

- 每次重大修改后，必须更新本文档。
- 采用时间倒序维护，最新记录放在最上方。
- 每次记录至少包含：日期、变更主题、新增/变更功能、影响接口、验证方式。
- 本文档只记录“已实现能力”；PRD/Jira 中的规划项不并入“已实现”口径。

## 项目概览（技术栈与当前边界）

- 技术栈：FastAPI、SQLAlchemy 2.x、MySQL（测试中使用 SQLite 内存库）。
- 当前后端边界：
  - 岗位管理与发布（含发布状态同步）。
  - 候选人导入/去重与评分。
  - 面试排期、约面执行与状态回写。
  - AI 简历解析与标准化（结构化画像与风险标签）。
  - AI 批量评分与岗位排序入围（shortlist）。
  - LLM 平台基础层（模型路由、Prompt 版本、审计追踪、策略门控骨架）。
  - 会话自动化（打招呼、消息同步、自动回复）。
  - BOSS 连接器（mock 与 live 均具备发布、状态同步、候选人拉取、会话能力）。
  - 统一响应封装、异常分层、写操作幂等中间件。

实现依据：
- `README.md`
- `ai_hr/main.py`
- `ai_hr/core/config.py`

## 已实现 API 能力

### Jobs

- `POST /api/v1/jobs`：创建岗位（初始状态 `draft`）。
- `GET /api/v1/jobs/{job_id}`：查询岗位详情（含发布记录）。
- `POST /api/v1/jobs/{job_id}/publish`：发布岗位到指定渠道（当前支持 `boss`）。
- `GET /api/v1/jobs/{job_id}/publish-status`：同步并查询发布状态。
- `POST /api/v1/jobs/{job_id}/candidates/sync`：按渠道拉取候选人并增量同步。
- `GET /api/v1/jobs/{job_id}/shortlist`：查询岗位 AI 入围名单。

实现依据：
- `ai_hr/api/routes/jobs.py`
- `ai_hr/schemas/jobs.py`
- `ai_hr/services/jobs.py`
- `ai_hr/repositories/jobs.py`
- `tests/test_ai_hr_jobs.py`
- `tests/test_ai_hr_ai_scoring.py`

### Interviews

- `POST /api/v1/interviews/schedule`：创建面试排期记录。
- `POST /api/v1/interviews/{interview_id}/dispatch`：执行 BOSS 约面。
- `POST /api/v1/interviews/{interview_id}/sync-status`：同步并回写约面状态。
- `GET /api/v1/interviews/{interview_id}`：查询面试记录。

实现依据：
- `ai_hr/api/routes/interviews.py`
- `ai_hr/schemas/interviews.py`
- `ai_hr/services/interviews.py`
- `ai_hr/repositories/interviews.py`
- `ai_hr/connectors/boss.py`
- `tests/test_ai_hr_interviews.py`

### Candidates

- `POST /api/v1/candidates/import`：候选人批量导入与 upsert。
- `POST /api/v1/candidates/{candidate_id}/score`：候选人评分并回写结果。
- `GET /api/v1/candidates/{candidate_id}/resume-profile`：查询候选人简历结构化画像。

实现依据：
- `ai_hr/api/routes/candidates.py`
- `ai_hr/schemas/candidates.py`
- `ai_hr/services/candidates.py`
- `ai_hr/repositories/candidates.py`
- `tests/test_ai_hr_jobs.py`

### AI

- `POST /api/v1/ai/resume/parse`：简历解析并写入结构化画像。
- `POST /api/v1/ai/resume/normalize`：简历字段标准化并刷新风险标签。
- `POST /api/v1/ai/candidates/score`：按岗位批量评分并落库。
- `POST /api/v1/ai/candidates/rank`：按评分结果排序并生成 shortlist。
- `POST /api/v1/ai/reply/classify-intent`：独立意图分类。
- `POST /api/v1/ai/reply/generate`：独立自动回复生成（含可解释输出）。
- `PUT /api/v1/ai/runtime/feature-flags/{feature_key}`：运行时开关管理。
- `POST /api/v1/ai/runtime/feature-flags/{feature_key}/rollback`：一键回滚到 `rule_only`。
- `PUT /api/v1/ai/runtime/model-configs/{task_key}`：运行时模型配置管理。
- `PUT /api/v1/ai/runtime/prompts/{task_key}`：运行时 Prompt 版本管理。
- （平台层）已支持 LLM 运行时路由、契约校验、guardrail、策略决策与 trace/decision 落库（当前默认 `mock` provider）。

### AI Interviews

- `POST /api/v1/ai/interviews/sessions`：创建 AI 面试会话（支持中英文与路由策略）。
- `POST /api/v1/ai/interviews/sessions/{session_id}/start`：启动会话。
- `POST /api/v1/ai/interviews/sessions/{session_id}/events`：实时事件写入（幂等去重、阶段推进、策略决策）。
- `POST /api/v1/ai/interviews/sessions/{session_id}/question-set/generate`：问题集生成与版本化。
- `POST /api/v1/ai/interviews/sessions/{session_id}/handoff`：人工接管。
- `POST /api/v1/ai/interviews/sessions/{session_id}/finish`：结束会话。
- `GET /api/v1/ai/interviews/sessions/{session_id}/report`：查询报告（支持 `run_id` 可复算）。
- `GET /api/v1/ai/interviews/sessions/{session_id}/replay`：会话回放（音频+转写，turn 粒度）。
- `GET /api/v1/ai/interviews/metrics`：治理指标（handoff_rate/blocked_rate/latency_p95）与告警原因。
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/join`：RTC 入会（房间鉴权与连接参数下发）。
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/reconnect`：RTC 重连（重连次数与原因留痕）。
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream`：ASR 流式适配（转写结果/置信度/延迟目标判定）。
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream`：TTS 流式播报（文本分片与音频地址）。

实现依据：
- `ai_hr/api/routes/ai.py`
- `ai_hr/schemas/ai_resume.py`
- `ai_hr/services/ai_resume.py`
- `ai_hr/repositories/resume_profiles.py`
- `ai_hr/db/models/candidate_resume_profile.py`
- `ai_hr/db/models/candidate_resume_risk.py`
- `tests/test_ai_hr_ai_resume.py`
- `ai_hr/schemas/ai_scoring.py`
- `ai_hr/services/ai_scoring.py`
- `ai_hr/repositories/ai_scoring.py`
- `ai_hr/db/models/candidate_job_score.py`
- `ai_hr/db/models/job_shortlist.py`
- `tests/test_ai_hr_ai_scoring.py`
- `ai_hr/services/llm/client.py`
- `ai_hr/services/llm/router.py`
- `ai_hr/services/llm/contracts.py`
- `ai_hr/services/llm/guardrails.py`
- `ai_hr/services/policy/decision.py`
- `ai_hr/repositories/ai_runtime.py`
- `ai_hr/repositories/ai_observability.py`
- `ai_hr/db/models/ai_model_config.py`
- `ai_hr/db/models/ai_prompt_version.py`
- `ai_hr/db/models/ai_feature_flag.py`
- `ai_hr/db/models/ai_request_trace.py`
- `ai_hr/db/models/ai_decision_log.py`
- `tests/test_ai_hr_llm_platform.py`

### Conversations

- `POST /api/v1/conversations/greet`：按候选人发起打招呼并创建/关联会话。
- `POST /api/v1/conversations/{conversation_id}/sync`：同步会话消息并增量游标拉取。
- `POST /api/v1/conversations/reply`：手动回复或自动回复（低置信度转人工状态）。

实现依据：
- `ai_hr/api/routes/conversations.py`
- `ai_hr/schemas/conversations.py`
- `ai_hr/services/conversations.py`
- `ai_hr/repositories/conversations.py`
- `ai_hr/repositories/events.py`
- `tests/test_ai_hr_jobs.py`

### System

- `GET /health`：服务健康检查（返回状态与环境）。
- 全局异常处理：422/404/400/500 统一返回 Envelope 结构。

实现依据：
- `ai_hr/main.py`
- `ai_hr/core/responses.py`
- `ai_hr/core/exceptions.py`

## 连接器与渠道能力（BOSS）

- 连接器注册与工厂化创建：当前注册渠道 `boss`。
- `mock` 模式：
  - 可发布岗位（返回模拟 `external_job_id`）。
  - 可同步岗位状态（返回 `published`）。
  - 可分页拉取候选人（支持 `cursor` 与 `has_more`）。
  - 可发送打招呼、拉取消息、发送消息。
- `live` 模式：
  - 已实现发布岗位能力（构造真实请求、解析返回、错误处理）。
  - 已实现状态同步能力（请求状态接口并归一化 `status`）。
  - 已实现候选人拉取能力（请求候选人列表接口，支持 cursor 分页）。
  - 已实现打招呼、会话消息同步、消息发送能力。
  - 已实现 Cookie/Header 解析（支持环境变量、配置文件、credential 文件）。

实现依据：
- `ai_hr/connectors/registry.py`
- `ai_hr/connectors/boss.py`
- `ai_hr/services/jobs.py`
- `tests/test_ai_hr_jobs.py`

## 数据与流程能力

- 候选人导入去重：
  - 先按 `(source_channel, external_candidate_id)` 命中身份映射。
  - 未命中时按 `phone_hash/email_hash` 合并主档。
  - 维护 `candidate_identities` 做跨外部 ID 归并。
- 评分回写：
  - 回写总分、维度分、解释、评分时间。
  - 阶段流转：`new -> parsed`，高分可进入 `screen_pass`。
- 简历画像与标准化：
  - 解析简历文本并生成结构化字段（技能、年限、学历、项目提示）。
  - 标准化字段值并持久化到 `candidate_resume_profiles`。
  - 风险标签持久化到 `candidate_resume_risks`（如技能缺失、年限缺失、文本过短）。
- 批量评分与筛选排序：
  - 按岗位维度批量评分并写入 `candidate_job_scores`。
  - 评分输出总分、维度分、解释、风险标签、评分版本。
  - 基于稳定排序规则生成 `job_shortlists` 并提供查询接口。
- 发布记录与状态管理：
  - 记录渠道发布请求/响应、错误信息、外部岗位 ID。
  - 支持发布状态同步回写与发布时间维护。
- 游标增量同步：
  - 每次按 `max_pages` 拉取候选人。
  - 持久化 `applicant_sync_cursor`，支持多轮增量拉取。
- 会话消息入库与事件记录：
  - 消息同步和发送都写入 `conversations.context_payload`。
  - 关键动作写入 `events`（greet/sync/reply）。

实现依据：
- `ai_hr/repositories/candidates.py`
- `ai_hr/repositories/jobs.py`
- `ai_hr/services/jobs.py`
- `ai_hr/services/candidates.py`
- `ai_hr/services/ai_resume.py`
- `ai_hr/services/ai_scoring.py`
- `tests/test_ai_hr_jobs.py`
- `tests/test_ai_hr_ai_resume.py`
- `tests/test_ai_hr_ai_scoring.py`

## 稳定性与治理能力

- 统一响应 Envelope：`ok/schema_version/data/error`。
- 异常分层：
  - 领域异常（如资源不存在、连接器错误）统一映射响应码。
  - 未知异常统一 500。
- 幂等中间件：
  - 对写请求支持 `X-Idempotency-Key`。
  - 相同 key + 相同请求体复用结果。
  - 相同 key + 不同请求体返回 `idempotency_conflict`。
  - 处理中重复提交返回 `idempotency_in_progress`。

实现依据：
- `ai_hr/core/responses.py`
- `ai_hr/core/exceptions.py`
- `ai_hr/core/idempotency.py`
- `ai_hr/main.py`
- `tests/test_ai_hr_jobs.py`

## 未覆盖能力（当前未实现）

以下条目来自现有 PRD/功能分析/Jira 语义，但在当前代码中未形成可调用后端能力（按公开 API 口径）：

- 面试自动排期与改期
- ATS 阶段看板与批量流转操作
- 审批流与完整审计查询接口
- 漏斗/KPI 统计分析接口
- 多渠道（智联/猎聘/拉勾等）连接器落地

参考来源（仅用于“未实现”识别，不作为已实现依据）：
- `docs/AI-HR-功能分析列表.md`
- `docs/AI-HR-可执行PRD-v1.md`
- `docs/AI-HR-Jira任务清单-v1.md`

## 变更记录

### 2026-03-21（13）

- 变更主题：S5 数据治理增强（DB-002A/DB-003A 生产化补齐）
- 新增/变更功能：
  - 新增 DB-002A 索引回滚脚本：`sql/migrations/20260321_ai_interview_online_indexes_rollback.sql`
  - `init_mysql.sql` 补齐 AI 面试生命周期相关索引，避免新环境与迁移环境索引漂移
  - 生命周期清理任务新增审计事件 `ai_interview.lifecycle.cleanup`，输出清理统计与执行模式（dry-run/real-run）
- 影响接口：
  - 无新增 HTTP API；增强离线治理脚本与审计事件
- 验证方式：
  - 新增 `tests/test_ai_hr_db_migrations.py`
  - 更新 `tests/test_ai_hr_lifecycle.py`
  - 回归：`uv run --project AI-HR pytest -q AI-HR/tests/test_ai_hr_lifecycle.py AI-HR/tests/test_ai_hr_db_migrations.py`

### 2026-03-21（12）

- 变更主题：S4 实时编排器服务化与降级矩阵落地
- 新增/变更功能：
  - 新增 `RealtimeOrchestrator`，统一编排 ASR->策略决策->追问->TTS
  - 事件链路新增降级可观测字段：`degradation_mode`、`latency_breakdown`
  - 新增分段时延指标：`asr_p95_ms`、`llm_p95_ms`、`tts_p95_ms`、`e2e_p95_ms`
  - 新增压测脚本骨架：`scripts/ai_interview_load_test.py`
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/events`（新增 `seq`、`audio_base64` 入参与编排输出字段）
  - `GET /api/v1/ai/interviews/metrics`（扩展分段时延指标）
- 验证方式：
  - 新增 `tests/test_ai_hr_orchestrator.py`
  - 全量回归：`uv run --project AI-HR pytest -q AI-HR/tests` -> `69 passed`

### 2026-03-21（11）

- 变更主题：生产级改造第一批（Provider治理 + RTC网关抽象 + 语音Provider抽象 + LLM面试题/追问）
- 新增/变更功能：
  - 新增 Provider 健康检查：`GET /health/providers`
  - 新增 Provider 熔断状态快照能力（进程内）
  - 新增 RTC 网关抽象层（mock/livekit 工厂）
  - 会话创建、RTC 入会、RTC 重连改为走 RTC provider
  - 新增语音 provider 抽象层（ASR/TTS，支持 mock/openai）
  - 面试题生成与追问支持 LLM 引擎开关（feature flag：`ai_interview_llm`）
- 影响接口：
  - `GET /health/providers`
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream`（新增 `audio_base64` 入参）
- 验证方式：
  - 新增 `tests/test_ai_hr_provider_health.py`
  - 新增 `tests/test_ai_hr_speech_providers.py`
  - 更新 `tests/test_ai_hr_ai_interviews.py`（LLM题目与追问用例）
  - 全量回归：`uv run --project AI-HR pytest -q AI-HR/tests` -> `67 passed`

### 2026-03-20（10）

- 变更主题：补齐 RTC-001/002/003（网关入会重连 + ASR/TTS 适配）
- 新增/变更功能：
  - 新增 RTC 入会接口与重连接口，支持连接留痕与可重连会话
  - 新增 ASR 流式适配接口，返回转写文本、置信度、延迟目标是否达标
  - 新增 TTS 流式播报接口，返回文本分片和模拟音频 URI
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/join`
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/reconnect`
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream`
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream`
- 验证方式：
  - `tests/test_ai_hr_ai_interviews.py` 新增 RTC 相关用例
  - 全量回归：`uv run --project AI-HR pytest -q AI-HR/tests` 通过

### 2026-03-20（9）

- 变更主题：AI 面试官模块全量闭环交付（BE/RTC/DB/QA 清单清零）
- 新增/变更功能：
  - 会话全生命周期：创建、开始、事件、转人工、结束、报告、回放
  - 阶段状态机：`intro/core/deep_dive/closing` 可观测且可重入
  - 追问策略：低置信与敏感策略分支全覆盖，输出可解释字段
  - 报告版本化：`run_id` 可复算，可按 run_id 精确查询
  - 治理指标接口：handoff_rate/blocked_rate/latency_p95 + 告警原因
  - 多模型路由策略：`cost_first/balanced/quality_first`
  - 数据治理：AI 面试表索引优化、转写/音频保留 TTL 落地
  - 审计增强：支持 operator/session_id/job_id 过滤
- 影响接口：
  - `GET /api/v1/ai/interviews/sessions/{session_id}/report?run_id=&force_recompute=`
  - `GET /api/v1/ai/interviews/sessions/{session_id}/replay`
  - `GET /api/v1/ai/interviews/metrics`
  - `GET /api/v1/audit/events`（新增 operator/session_id/job_id 过滤）
- 验证方式：
  - 增量回归：`19 passed`
  - 全量回归：`uv run --project AI-HR pytest -q AI-HR/tests` -> `61 passed`

### 2026-03-20（6）

- 变更主题：实现 AHR-BE-016/017（面试排期 + BOSS 约面执行与状态回写）
- 新增/变更功能：
  - 新增面试排期 API：`/api/v1/interviews/schedule`
  - 新增约面执行 API：`/api/v1/interviews/{id}/dispatch`
  - 新增状态回写 API：`/api/v1/interviews/{id}/sync-status`
  - BOSS 连接器新增 `schedule_interview` 与 `sync_interview_status`（mock/live）
- 影响接口：
  - `POST /api/v1/interviews/schedule`
  - `POST /api/v1/interviews/{interview_id}/dispatch`
  - `POST /api/v1/interviews/{interview_id}/sync-status`
  - `GET /api/v1/interviews/{interview_id}`
- 验证方式：
  - 新增 `tests/test_ai_hr_interviews.py`
  - 全量回归：`pytest -q` 共 36 条通过

### 2026-03-20（5）

- 变更主题：实现 AHR-AI-007/008（意图分类接口化 + 自动回复生成接口化）
- 新增/变更功能：
  - 新增独立 AI 回复接口：`/ai/reply/classify-intent`、`/ai/reply/generate`
  - `AIReplyLLMService` 支持独立分类与生成方法，保留旧会话链路兼容
  - 回复生成结果新增可解释字段（意图依据、动作原因、策略标记）
- 影响接口：
  - `POST /api/v1/ai/reply/classify-intent`
  - `POST /api/v1/ai/reply/generate`
- 验证方式：
  - 新增 `tests/test_ai_hr_ai_reply.py`
  - 全量回归：6 组测试共 32 条通过

### 2026-03-20（4）

- 变更主题：实现 LLM 运行时管理 API + 回滚开关
- 新增/变更功能：
  - 新增运行时管理路由：feature flag、model config、prompt config 的查询与写入
  - 新增回滚接口：`/ai/runtime/feature-flags/{feature_key}/rollback`
  - 业务链路开关升级：`AIResume/AIScoring/Conversation` 支持运行时开关优先于静态配置
- 影响接口：
  - `PUT /api/v1/ai/runtime/feature-flags/{feature_key}`
  - `GET /api/v1/ai/runtime/feature-flags/{feature_key}`
  - `POST /api/v1/ai/runtime/feature-flags/{feature_key}/rollback`
  - `PUT /api/v1/ai/runtime/model-configs/{task_key}`
  - `GET /api/v1/ai/runtime/model-configs/{task_key}`
  - `PUT /api/v1/ai/runtime/prompts/{task_key}`
  - `GET /api/v1/ai/runtime/prompts/{task_key}`
- 验证方式：
  - 新增 `tests/test_ai_hr_ai_runtime.py`
  - 全量回归：5 组测试共 30 条通过

### 2026-03-20（3）

- 变更主题：LLM 生产化阶段 A（平台基础层）落地
- 新增/变更功能：
  - 新增 LLM 平台模块：`client/router/prompts/contracts/guardrails/fallback`
  - 新增策略层：`PolicyDecisionService`（自动发送/转人工/拦截决策）
  - 新增运行时与审计模型：模型配置、Prompt 版本、灰度开关、请求 trace、决策日志
  - `AIResume`、`AIScoring`、`Conversation` 增加 LLM 开关位接入（默认关闭，不影响现有线上行为）
- 影响接口：
  - 公共 API 路径不变（保持兼容）
  - 内部 AI 执行链路新增 LLM 路由与审计能力
- 验证方式：
  - 新增 `tests/test_ai_hr_llm_platform.py`
  - 全量回归：`tests/test_ai_hr_llm_platform.py + tests/test_ai_hr_ai_resume.py + tests/test_ai_hr_ai_scoring.py + tests/test_ai_hr_jobs.py` 共 28 条通过

### 2026-03-20（2）

- 变更主题：实现 AHR-AI-004/005（批量评分 + 筛选排序 + 风险标签增强）
- 新增/变更功能：
  - 新增 AI 评分接口：`/api/v1/ai/candidates/score`、`/api/v1/ai/candidates/rank`
  - 新增岗位入围查询：`/api/v1/jobs/{job_id}/shortlist`
  - 新增数据表模型：`candidate_job_scores`、`job_shortlists`
  - 评分引擎增强：输出 `score_version` 与 `risk_tags`
- 影响接口：
  - `POST /api/v1/ai/candidates/score`
  - `POST /api/v1/ai/candidates/rank`
  - `GET /api/v1/jobs/{job_id}/shortlist`
- 验证方式：
  - `tests/test_ai_hr_ai_scoring.py` 新增 2 条用例并通过
  - 全量回归：`tests/test_ai_hr_ai_resume.py + tests/test_ai_hr_ai_scoring.py + tests/test_ai_hr_jobs.py` 共 26 条通过

### 2026-03-20（1）

- 变更主题：实现 AHR-AI-001/002/003（简历 Schema + 解析 + 标准化）
- 新增/变更功能：
  - 新增 AI 简历接口：`/api/v1/ai/resume/parse`、`/api/v1/ai/resume/normalize`
  - 新增候选人画像查询：`/api/v1/candidates/{candidate_id}/resume-profile`
  - 新增数据表模型：`candidate_resume_profiles`、`candidate_resume_risks`
  - 新增简历画像仓储与服务，支持解析、标准化、风险识别、置信度写回
- 影响接口：
  - `POST /api/v1/ai/resume/parse`
  - `POST /api/v1/ai/resume/normalize`
  - `GET /api/v1/candidates/{candidate_id}/resume-profile`
- 验证方式：
  - `tests/test_ai_hr_ai_resume.py` 新增 4 条用例并通过
  - 全量回归：`tests/test_ai_hr_ai_resume.py + tests/test_ai_hr_jobs.py` 共 24 条通过

### 2026-03-19（3）

- 变更主题：实现 BE-013/014/015（打招呼 + 会话同步 + 自动回复）
- 新增/变更功能：
  - 新增 conversations API：`/greet`、`/{id}/sync`、`/reply`
  - 新增会话仓储与事件仓储，支持消息持久化和事件审计
  - BOSS 连接器新增 `send_greeting`、`fetch_messages`、`send_message`（mock/live）
- 影响接口：
  - `POST /api/v1/conversations/greet`
  - `POST /api/v1/conversations/{conversation_id}/sync`
  - `POST /api/v1/conversations/reply`
- 验证方式：
  - `tests/test_ai_hr_jobs.py` 新增 conversations 与 live connector 用例并通过

### 2026-03-19（2）

- 变更主题：补齐 BOSS live 的状态同步与候选人拉取实现
- 新增/变更功能：
  - 新增 `AI_HR_BOSS_STATUS_PATH`、`AI_HR_BOSS_APPLICANTS_PATH` 配置项
  - `boss` 连接器在 live 模式下支持 `sync_job_status` 和 `list_applicants`
  - 增加对应自动化测试覆盖
- 影响接口：
  - `GET /api/v1/jobs/{job_id}/publish-status`
  - `POST /api/v1/jobs/{job_id}/candidates/sync`
- 验证方式：
  - `tests/test_ai_hr_jobs.py` 新增 live 相关用例并通过

### 2026-03-19（1）

- 变更主题：建立“已实现功能清单”基线文档
- 新增/变更功能：
  - 首次按“仅已实现”口径梳理 Jobs/Candidates/System/Connector/治理能力
  - 明确列出“当前未实现”功能边界
- 影响接口：
  - 文档层变更，不影响任何 API/Schema/数据库结构
- 验证方式：
  - 对照 `routes/services/repositories/tests` 逐项核对

### 2026-03-20（6）

- 变更主题：实现 AHR-AI-010（按岗位人数自动邀约计划与发送编排）
- 新增/变更功能：
  - 新增面试计划接口：`POST /api/v1/jobs/{job_id}/interview/plan`
  - 新增面试发送接口：`POST /api/v1/jobs/{job_id}/interview/send`
  - 新增面试进度接口：`GET /api/v1/jobs/{job_id}/interview/progress`
  - 新增岗位维度面试统计：总目标、已发送、成功、失败、待确认
  - 新增不超发与幂等保护：同岗位同候选人避免重复创建邀约
- 影响接口：
  - `POST /api/v1/jobs/{job_id}/interview/plan`
  - `POST /api/v1/jobs/{job_id}/interview/send`
  - `GET /api/v1/jobs/{job_id}/interview/progress`
- 验证方式：
  - `tests/test_ai_hr_interviews.py` 新增 plan/send/progress 用例
  - 回归结果：`7 passed`

### 2026-03-20（7）

- 变更主题：实现 AHR-AI-012（离线评测运行与报告接口最小可执行版）
- 新增/变更功能：
  - 新增评测运行接口：`POST /api/v1/ai/eval/run`
  - 新增评测报告接口：`GET /api/v1/ai/eval/report`
  - 新增评测运行模型：`ai_eval_runs`
  - 新增评测服务与仓储：支持按 `eval_type` 查询最新报告，支持按 `run_id` 精确查询
- 影响接口：
  - `POST /api/v1/ai/eval/run`
  - `GET /api/v1/ai/eval/report`
- 验证方式：
  - 新增 `tests/test_ai_hr_ai_eval.py`
  - 回归结果：`tests/test_ai_hr_interviews.py + tests/test_ai_hr_ai_eval.py` -> `10 passed`

### 2026-03-20（8）

- 变更主题：治理路由接入（审批/审计/漏斗）
- 新增/变更功能：
  - 治理接口接入主路由并对外可用：
    - `POST /api/v1/approvals`
    - `POST /api/v1/approvals/{approval_id}/decision`
    - `GET /api/v1/audit/events`
    - `GET /api/v1/metrics/funnel`
- 影响接口：
  - `POST /api/v1/approvals`
  - `POST /api/v1/approvals/{approval_id}/decision`
  - `GET /api/v1/audit/events`
  - `GET /api/v1/metrics/funnel`
- 验证方式：
  - 新增 `tests/test_ai_hr_governance.py`
  - 专项回归：`2 passed`
  - 全量回归：`44 passed`

### 2026-03-21（13）

- 变更主题：LiveKit 真链路第一轮补齐（候选人音轨订阅）
- 新增/变更功能：
  - 新增 RTC 音轨订阅接口：`POST /api/v1/ai/interviews/sessions/{session_id}/rtc/audio/subscribe`
  - RTC 网关抽象新增 `subscribe_audio_tracks()`，mock/livekit provider 均已支持
  - LiveKit 网关新增 `UpdateSubscriptions` 调用（可按 `track_sids` 精确订阅）
  - 会话 payload 与审计事件新增音轨订阅回写：`ai_interview.rtc.audio_subscribe`
  - 新增开关与降级路径：`AI_HR_AI_INTERVIEW_RTC_AUDIO_SUBSCRIBE_ENABLED`（关闭即跳过订阅）
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/audio/subscribe`
  - 配置新增：`AI_HR_LIVEKIT_UPDATE_SUBSCRIPTIONS_PATH`
- 验证方式：
  - 新增 `tests/test_ai_hr_rtc_gateway.py`
  - 更新 `tests/test_ai_hr_ai_interviews.py`

### 2026-03-21（14）

- 变更主题：ASR 流式真链路（分片输入 + 实时回写增强）
- 新增/变更功能：
  - ASR 接口支持音频分片输入：`chunk_id/chunk_index/chunk_total/is_final/input_format`
  - ASR 响应新增实时链路字段：`event_id/turn_id/deduplicated/is_partial/target_latency_ms/realtime_target_met/latency_breakdown`
  - turns 回写增强：非 final 分片落 `candidate_partial`，final 分片落 `candidate`
  - audit events 回写增强：`ai_interview.rtc.asr` 事件记录分片信息与延迟分解
  - 幂等增强：同一 `chunk_id` 重复请求可去重
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream`（兼容扩展）
- 验证方式：
  - 新增 `tests/test_ai_hr_asr_streaming.py`
  - 增量回归：`pytest test_ai_hr_asr_streaming.py test_ai_hr_ai_interviews.py`
  - 全量回归：`pytest tests` -> `82 passed`

### 2026-03-21（15）

- 变更主题：TTS 回灌真链路（文本 -> 音频流 -> AI bot 轨道发布）
- 新增/变更功能：
  - TTS 接口增强发布控制参数：`publish_to_rtc/bot_identity/track_name/target_latency_ms`
  - RTC 网关新增 `publish_bot_audio()`；mock provider 返回模拟 bot track，livekit provider 走 `RoomService.SendData`
  - TTS 结果回写到会话 turns（`speaker=ai`）并记录发布状态
  - 审计事件 `ai_interview.rtc.tts` 增加发布状态与链路时延分解字段
  - 新增实时时延达标判定：`realtime_target_met`、`p95_target_met`
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream`（兼容扩展）
  - 新增配置：`AI_HR_LIVEKIT_SEND_DATA_PATH`、`AI_HR_AI_INTERVIEW_RTC_TTS_PUBLISH_ENABLED`、`AI_HR_AI_INTERVIEW_RTC_TTS_BOT_IDENTITY`
- 验证方式：
  - 新增 `tests/test_ai_hr_tts_streaming.py`
  - 更新 `tests/test_ai_hr_rtc_gateway.py`
  - 全量回归：`pytest tests` -> `86 passed`

### 2026-03-21（16）

- 变更主题：视频轨策略落地（候选人视频上行 + AI 订阅/录制）
- 新增/变更功能：
  - 新增视频策略接口：`POST /api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy`
  - RTC 网关新增 `apply_video_policy()`，mock/livekit 均支持
  - 会话与审计回写视频策略执行结果：`ai_interview.rtc.video_policy`
  - 指标新增视频策略覆盖率与录制启用率
- 影响接口：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy`
  - `GET /api/v1/ai/interviews/metrics`（新增视频策略指标）
- 验证方式：
  - 新增 `tests/test_ai_hr_video_policy.py`
  - 更新 `tests/test_ai_hr_rtc_gateway.py`
  - 全量回归：`pytest tests` -> `91 passed`

### 2026-03-21（17）

- 变更主题：正式接入腾讯云语音服务（ASR/TTS）
- 新增/变更功能：
  - 新增 Tencent ASR Provider（SentenceRecognition，TC3-HMAC-SHA256 鉴权）
  - 新增 Tencent TTS Provider（TextToVoice，TC3-HMAC-SHA256 鉴权）
  - `speech.factory` 新增 `provider=tencent` 分支
  - 新增腾讯云配置项（`AI_HR_TENCENT_SECRET_ID/SECRET_KEY/REGION` 等）
  - 新增测试隔离 `tests/conftest.py`，避免本地 `.env.dev` 污染回归
- 影响接口：
  - 无新增 HTTP API；增强 ASR/TTS provider 能力
- 验证方式：
  - 更新 `tests/test_ai_hr_speech_providers.py`
  - 全量回归：`pytest tests` -> `93 passed`

## 2026-03-22 增量更新（实时低延迟链路）
- 腾讯 ASR：已支持 WebSocket 优先模式，异常时自动降级到 HTTP 句识别。
- 前端采集：已改为 AudioWorklet，降低浏览器采集和主线程阻塞。
- LLM 实时追问：增加短上下文和去重缓存，减少重复追问与首响应等待。
- 腾讯 TTS：增加 warmup 钩子与首包优先分片。
- 实时事件总线：新增 WebSocket 订阅接口，实时推送字幕和会话状态。

## 2026-03-22 第二轮增量
- 腾讯 ASR 支持持续双工分帧会话（session+seq 复用 WS）。
- 前端 VAD 新增噪声自适应阈值，提升停顿检测稳定性。
- 新增 E2E 压测脚本，可输出 ASR/LLM/TTS/e2e 的 P50/P95 指标。

## 2026-03-22 第三轮增量（全双工）
- 新增 `rtc/duplex/ws`，实现单通道音频上行与识别/追问下行。
- 前端升级为 duplex 优先，显著减少 HTTP 串行调用与重复 TTS。
- 提供开关回滚到原有链路，便于灰度发布。

## 2026-03-22 第四轮增量（全双工细化）
- 前端音频上行改为固定 30ms 帧持续上传。
- duplex 通道新增首包语音推送事件，支持更快起播。
- E2E 压测支持 legacy/duplex 对比，已验证 e2e P95 明显下降。

## 2026-03-22 第五轮增量（协议与流式）
- duplex 协议支持 ack + frame_id + 重传 + 去重。
- duplex TTS 改为 packet 级流式推送（duplex.tts.packet）。
- 压测对比显示 e2e P95 持续下降，但 ASR 仍是主瓶颈。
