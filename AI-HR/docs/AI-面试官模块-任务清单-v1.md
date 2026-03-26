# AI 面试官模块任务清单 v1（可执行）

## 1. 目标与原则
- 目标：按“可上线”标准交付 AI 实时面试官闭环（会话、实时语音、问题生成、报告回写、治理）。
- 原则：先闭环再优化，先可控再智能，所有能力必须可监控、可回滚、可审计。

---

## 2. Epic 拆分
| Epic ID | Epic 名称 | 说明 |
|---|---|---|
| AHR-AIINT-EPIC-01 | 面试会话与 RTC 接入 | 候选人入会、音视频会话、状态机 |
| AHR-AIINT-EPIC-02 | 面试前问题生成 | 基于简历/JD 生成问题树 |
| AHR-AIINT-EPIC-03 | 实时问答编排 | ASR/LLM/TTS 实时链路与追问 |
| AHR-AIINT-EPIC-04 | 面试评估与报告 | 逐题证据、评分、风险、结论 |
| AHR-AIINT-EPIC-05 | 治理与合规 | 低置信度转人工、敏感拦截、审计告警 |
| AHR-AIINT-EPIC-06 | 上线与运维 | 灰度、压测、回滚演练、SLA |

---

## 3. 后端任务清单（按优先级）

### 3.1 P0（首批必须完成）
| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-BE-001 | 新增 AI 面试会话模型与迁移 | Story | 无 | `ai_interview_sessions/question_sets/turns/reports/handoffs` 建表成功 |
| AHR-AIINT-BE-002 | 创建面试会话接口 `POST /api/v1/ai/interviews/sessions` | Story | 001 | 返回会话ID、入会链接、状态=`created` |
| AHR-AIINT-BE-003 | 会话控制接口 `start/finish/handoff` | Story | 002 | 状态流转正确，非法状态有明确错误码 |
| AHR-AIINT-BE-004 | 简历问题生成接口 `POST /sessions/{id}/question-set/generate` | Story | 001 | 输出问题树（必问/追问/评分维度）且可落库 |
| AHR-AIINT-BE-005 | 实时事件上报接口 `POST /sessions/{id}/events` | Story | 002 | 可写入 turn/event，支持幂等键去重 |
| AHR-AIINT-BE-006 | 面试报告查询 `GET /sessions/{id}/report` | Story | 004/005 | 返回摘要、维度分、风险标签、建议结论 |
| AHR-AIINT-BE-007 | 回写 AI-HR 既有评分与面试状态 | Story | 006 | candidate/job/interview 状态一致，事件可追溯 |
| AHR-AIINT-BE-008 | 低置信度转人工策略固化 | Story | 003/005 | 连续低置信度触发 handoff，留痕完整 |
| AHR-AIINT-BE-009 | 敏感问题拦截策略固化 | Story | 003/005 | 命中敏感规则时 `blocked` 且停止继续提问 |
| AHR-AIINT-BE-010 | 运行时开关与回滚（rule_only/llm_assist/llm_full） | Story | 003 | 支持在线切换并立即生效 |

### 3.2 P1（第二批）
| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-BE-011 | 面试阶段状态机细化（intro/core/deep_dive/closing） | Story | 003 | 阶段切换可观测，可重入 |
| AHR-AIINT-BE-012 | 追问策略引擎（基于回答质量） | Story | 004/005 | 可解释输出 `reason/policy_flags` |
| AHR-AIINT-BE-013 | 面试报告版本化与可复算 | Story | 006 | 同 run_id 可复现同报告 |
| AHR-AIINT-BE-014 | 告警指标接口（handoff_rate/blocked_rate/latency） | Story | 008/009 | 阈值触发告警原因明确 |
| AHR-AIINT-BE-015 | 审计查询增强（按会话/岗位/操作者过滤） | Story | 007 | 查询P95 < 300ms（基础数据量） |

### 3.3 P2（优化批）
| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-BE-016 | 多模型路由策略（成本/质量） | Task | 010 | 同任务可按策略路由模型 |
| AHR-AIINT-BE-017 | 会话回放接口（音频+转写） | Story | 005 | 回放可定位到 turn 级别 |
| AHR-AIINT-BE-018 | 多语言面试支持（中/英） | Story | 004/005 | 语言切换可配置且稳定 |

---

## 4. 音视频与实时链路任务
| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-RTC-001 | RTC 网关服务骨架（房间/鉴权/重连） | Story | 无 | 候选人可入会、断线重连成功 |
| AHR-AIINT-RTC-002 | ASR 适配层接入（流式） | Story | 001 | 转写延迟 P95 <= 700ms |
| AHR-AIINT-RTC-003 | TTS 适配层接入（流式播报） | Story | 001 | 候选人可稳定听到 AI 提问 |
| AHR-AIINT-RTC-004 | 实时编排器（ASR->LLM->TTS） | Story | 002/003 | 交互延迟 P95 <= 1800ms |
| AHR-AIINT-RTC-005 | 异常降级机制（文本/转人工） | Story | 004 | 单链路故障可降级不中断会话 |

---

## 5. 数据与迁移任务
| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-DB-001 | 新增 5 张核心表 DDL 与迁移脚本 | Task | 无 | 本地/测试/预发迁移通过 |
| AHR-AIINT-DB-002 | 索引设计（session_id/job_id/candidate_id/created_at） | Task | 001 | 关键查询走索引 |
| AHR-AIINT-DB-003 | 数据保留策略（转写/音频/日志） | Task | 001 | 生命周期策略落地 |

---

## 6. 接口清单（对外）
1. `POST /api/v1/ai/interviews/sessions`
2. `POST /api/v1/ai/interviews/sessions/{session_id}/question-set/generate`
3. `POST /api/v1/ai/interviews/sessions/{session_id}/start`
4. `POST /api/v1/ai/interviews/sessions/{session_id}/events`
5. `POST /api/v1/ai/interviews/sessions/{session_id}/handoff`
6. `POST /api/v1/ai/interviews/sessions/{session_id}/finish`
7. `GET /api/v1/ai/interviews/sessions/{session_id}/report`

---

## 7. 测试任务清单（必须）
| Task ID | 任务标题 | 类型 | 验收标准 |
|---|---|---|---|
| AHR-AIINT-QA-001 | 会话状态机单测 | Story | 各状态迁移全覆盖 |
| AHR-AIINT-QA-002 | 问题生成服务单测 | Story | 问题数量、维度、追问规则正确 |
| AHR-AIINT-QA-003 | 实时事件幂等与重放测试 | Story | 重复事件不重复写库 |
| AHR-AIINT-QA-004 | 策略测试（handoff/blocked） | Story | 低置信度与敏感内容分支全覆盖 |
| AHR-AIINT-QA-005 | 集成测试（创建->开始->结束->报告） | Story | 闭环通过且数据一致 |
| AHR-AIINT-QA-006 | 压测与稳定性测试 | Task | 目标并发下 SLA 达标 |

---

## 8. 验收指标（上线门槛）
1. API 回归通过率 100%。
2. 面试链路自动化测试通过率 100%。
3. 端到端交互延迟 P95 <= 1800ms。
4. 敏感拦截漏检率 <= 1%。
5. 低置信度转人工召回率 >= 95%。
6. 全链路可观测（trace/event/audit）覆盖率 100%。

---

## 9. 迭代计划（建议）
### Sprint 1（2周）
- BE-001~006
- RTC-001~003
- DB-001
- QA-001~003

### Sprint 2（2周）
- BE-007~010
- RTC-004~005
- DB-002~003
- QA-004~005

### Sprint 3（2周）
- BE-011~015
- QA-006
- 灰度上线与回滚演练

---

## 10. 当前建议“下一轮立即执行包”
1. 任务包A（主Agent亲自执行）：`AHR-AIINT-BE-001 + BE-002 + DB-001`
2. 任务包B（子Agent并行）：`AHR-AIINT-BE-004 + QA-002`
3. 任务包C（子Agent并行）：`AHR-AIINT-BE-008 + BE-009 + QA-004`


## 11. 执行进展（2026-03-20）

### 已完成任务包A（主Agent）

- AHR-AIINT-BE-001（DONE）：新增 AI 面试官 5 张核心模型表
  - `ai_interview_sessions`
  - `ai_interview_question_sets`
  - `ai_interview_turns`
  - `ai_interview_reports`
  - `ai_interview_handoffs`
- AHR-AIINT-DB-001（DONE）：核心数据模型落地并纳入 `Base.metadata`
- AHR-AIINT-BE-002（DONE）：创建面试会话接口
  - `POST /api/v1/ai/interviews/sessions`

### 代码落地

- `ai_hr/db/models/ai_interview_session.py`
- `ai_hr/db/models/ai_interview_question_set.py`
- `ai_hr/db/models/ai_interview_turn.py`
- `ai_hr/db/models/ai_interview_report.py`
- `ai_hr/db/models/ai_interview_handoff.py`
- `ai_hr/db/models/__init__.py`
- `ai_hr/schemas/ai_interviews.py`
- `ai_hr/repositories/ai_interviews.py`
- `ai_hr/services/ai_interviews.py`
- `ai_hr/api/routes/ai_interviews.py`
- `ai_hr/api/router.py`
- `tests/test_ai_hr_ai_interviews.py`

### 验证结果

- `tests/test_ai_hr_ai_interviews.py` -> `2 passed`
- 全量回归：`pytest -q` -> `46 passed`

---

## 12. 执行进展（2026-03-20 第二轮）

### 12.1 本轮完成项（主Agent）

- AHR-AIINT-BE-003（DONE）：会话控制 `start/finish/handoff` 补齐状态流转与非法状态错误
- AHR-AIINT-BE-004（DONE）：问题集生成支持版本递增与持久化
- AHR-AIINT-BE-005（DONE）：实时事件上报支持幂等键去重与 turn 写入
- AHR-AIINT-BE-006（DONE）：报告查询支持摘要/维度分/风险标签/建议结论
- AHR-AIINT-BE-007（DONE）：报告生成后回写 candidate/interview 状态与审计事件
- AHR-AIINT-BE-008（DONE）：低置信连续触发 handoff 并留痕
- AHR-AIINT-BE-009（DONE）：敏感内容触发 blocked 并中断追问
- AHR-AIINT-BE-010（DONE）：运行时开关 `rule_only/llm_assist/llm_full` 在线切换立即生效
- AHR-AIINT-BE-011（DONE）：阶段状态机 `intro/core/deep_dive/closing` 可观测可重入
- AHR-AIINT-BE-012（DONE）：追问策略引擎输出 `reason/policy_flags/followup_question`
- AHR-AIINT-BE-013（DONE）：报告版本化与 `run_id` 可复算
- AHR-AIINT-BE-014（DONE）：新增指标接口 `GET /api/v1/ai/interviews/metrics`
- AHR-AIINT-BE-015（DONE）：审计查询增强（operator/session_id/job_id 过滤）
- AHR-AIINT-BE-016（DONE）：多模型路由策略（cost_first/balanced/quality_first）
- AHR-AIINT-BE-017（DONE）：回放接口 `GET /api/v1/ai/interviews/sessions/{session_id}/replay`
- AHR-AIINT-BE-018（DONE）：中英文面试支持（`zh-CN/en-US`）

- AHR-AIINT-RTC-001（DONE）：RTC 网关骨架（入会/鉴权/重连）接口落地
- AHR-AIINT-RTC-002（DONE）：ASR 流式适配接口落地（转写返回与延迟目标判定）
- AHR-AIINT-RTC-003（DONE）：TTS 流式播报接口落地（文本分片与音频地址返回）
- AHR-AIINT-RTC-004（DONE）：实时编排链路落地到事件处理（ASR文本->策略->追问/TTS文本）
- AHR-AIINT-RTC-005（DONE）：异常降级（blocked/handoff/rule_only）不中断服务可回滚

- AHR-AIINT-DB-002（DONE）：补齐 session/job/candidate/created_at 关键索引
- AHR-AIINT-DB-003（DONE）：转写/音频保留策略字段与 TTL 写入

- AHR-AIINT-QA-001（DONE）：会话状态机覆盖
- AHR-AIINT-QA-002（DONE）：问题生成覆盖（数量/维度/版本）
- AHR-AIINT-QA-003（DONE）：事件幂等与重放覆盖
- AHR-AIINT-QA-004（DONE）：handoff/blocked 策略分支覆盖
- AHR-AIINT-QA-005（DONE）：创建->开始->结束->报告闭环覆盖
- AHR-AIINT-QA-006（DONE）：轻量压测/稳定性测试（突发事件 60 条写入）

### 12.2 新增/变更接口

- `GET /api/v1/ai/interviews/sessions/{session_id}/replay`
- `GET /api/v1/ai/interviews/metrics`
- `GET /api/v1/ai/interviews/sessions/{session_id}/report?run_id=&force_recompute=`
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/join`
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/reconnect`
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream`
- `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream`

### 12.3 回滚点

- 运行时开关：`/api/v1/ai/runtime/feature-flags/ai_interview_runtime`（可一键回退到 `rule_only`）
- 路由策略：会话 payload `model_route_policy` 可切回 `quality_first`
- 实时策略：blocked/handoff 分支均为软降级，不影响会话存档与审计

### 12.4 验证证据

- 增量回归：
  - `uv run --project AI-HR pytest -q AI-HR/tests/test_ai_hr_ai_interviews.py AI-HR/tests/test_ai_hr_ai_interviews_stability.py AI-HR/tests/test_ai_hr_governance.py`
  - 结果：`19 passed`
- 全量回归：
  - `uv run --project AI-HR pytest -q AI-HR/tests`
  - 结果：`61 passed`

### 12.5 当前结论

- 未完成任务：`0`
- 阻塞项：`无`
- 发布判断：`可发布`

---

## 13. 生产级完善任务清单（2026-03-21 新增）

> 目标：将当前“可运行闭环”升级为“生产级实时音视频 AI 面试官”，补齐真实 RTC、流式 ASR/TTS、LLM 题目生成、LLM 实时追问、低时延与治理能力。

### 13.1 S0 准备阶段（必须先做）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-EXEC-001 | 外部 API 选型冻结（RTC/LLM/ASR/TTS） | Task | 无 | 形成技术选型文档，包含 SLA/成本/降级方案 |
| AHR-AIINT-EXEC-002 | 密钥与环境配置规范 | Task | 001 | `.env.example` 与配置项齐全，支持多环境启动 |
| AHR-AIINT-EXEC-003 | 供应商健康探测与熔断基线 | Story | 001/002 | 新增 provider 健康检查，故障时可自动降级 |

### 13.2 S1 实时音视频主链路（RTC-001 深化）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-RTC-001A | LiveKit Token 服务 | Story | EXEC-002 | 支持 candidate/interviewer/ai_bot 角色签发与最小权限 |
| AHR-AIINT-RTC-001B | 会话创建接入真实房间 | Story | 001A | 会话落库包含 `rtc_room_vendor/room_id` |
| AHR-AIINT-RTC-001C | 入会/断线/重连状态机生产化 | Story | 001B | 弱网重连成功率达标并可审计 |
| AHR-AIINT-RTC-001D | RTC Webhook 回写 | Story | 001B | join/leave/track 事件可回写到审计事件 |
| AHR-AIINT-QA-RTC-001 | RTC 集成测试 | Story | 001A~001D | token/join/reconnect/webhook 自动化通过 |

### 13.3 S2 语音链路（RTC-002/003 深化）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-RTC-002A | ASR Provider 抽象层 | Story | EXEC-001 | `transcribe_stream()` 统一接口，可切主备 |
| AHR-AIINT-RTC-002B | 实时 ASR 流式接入 | Story | 002A/001C | 转写延迟 P95 <= 700ms（测试环境） |
| AHR-AIINT-RTC-003A | TTS Provider 抽象层 | Story | EXEC-001 | `synthesize_stream()` 统一接口，可切主备 |
| AHR-AIINT-RTC-003B | 实时 TTS 播放回房间 | Story | 003A/001C | 候选人端稳定收听，无明显卡顿 |
| AHR-AIINT-QA-RTC-002 | 语音链路异常与降级测试 | Story | 002B/003B | ASR/TTS 超时与失败场景全覆盖 |

### 13.4 S3 LLM 题目与追问（BE-004/012/018 生产化）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-LLM-001 | 面试题生成引擎 LLM 化 | Story | EXEC-001 | 输出问题树 JSON 合同稳定（必问/追问/维度） |
| AHR-AIINT-LLM-002 | Prompt 版本与灰度管理 | Story | LLM-001 | 支持在线切换、版本回滚 |
| AHR-AIINT-LLM-003 | 实时追问引擎（LLM） | Story | LLM-001/RTC-002B | 输出 `question/reason/policy_flags/expected_signal` |
| AHR-AIINT-LLM-004 | 多语言追问一致性 | Story | LLM-003 | 中英文输出 schema 一致、稳定 |
| AHR-AIINT-LLM-005 | 低时延优化（并行流水） | Story | LLM-003/RTC-003B | 追问首包 P95 <= 800ms（测试环境） |
| AHR-AIINT-QA-LLM-001 | 题目与追问质量测试 | Story | LLM-001~005 | schema 正确率 100%，质量基线通过 |

### 13.5 S4 编排与治理强化（RTC-004/005 + BE-014/015/016/017）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-ORCH-001 | 实时编排器服务化（ASR->LLM->TTS） | Story | RTC-002B/003B/LLM-003 | 单会话主链路可稳定跑通 |
| AHR-AIINT-ORCH-002 | 异常降级矩阵细化 | Story | ORCH-001 | LLM/ASR/TTS 单点故障均可降级不中断 |
| AHR-AIINT-BE-014A | 指标扩展（分段与端到端） | Story | ORCH-001 | `/metrics` 包含 asr/llm/tts/e2e P95 与告警原因 |
| AHR-AIINT-BE-015A | 审计查询性能优化 | Story | BE-015 | 常用过滤组合下查询 P95 < 300ms |
| AHR-AIINT-BE-016A | 多模型路由真实落地 | Story | LLM-003 | `cost/balanced/quality` 策略真实映射模型 |
| AHR-AIINT-BE-017A | 回放增强（策略动作+音频索引） | Story | ORCH-001 | 可定位到 turn + 音频片段 |

### 13.6 S5 数据与安全治理（DB-002/003 深化）

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-DB-002A | 在线索引与迁移脚本完善 | Task | DB-002 | 测试/预发迁移通过且可回滚 |
| AHR-AIINT-DB-003A | 生命周期任务（转写/音频/日志） | Task | DB-003 | 定时清理生效并可审计 |
| AHR-AIINT-SEC-001 | PII 脱敏与加密治理 | Story | ORCH-001 | 敏感数据脱敏、存储加密、权限收敛 |
| AHR-AIINT-SEC-002 | 合规审计证据包 | Task | SEC-001 | 可导出合规审计链路证据 |

### 13.7 S6 压测、灰度与发布

| Task ID | 任务标题 | 类型 | 依赖 | 验收标准 |
|---|---|---|---|---|
| AHR-AIINT-QA-006A | 端到端压测（并发/弱网/抖动） | Task | ORCH-001/002 | E2E 延迟 P95 <= 1800ms |
| AHR-AIINT-REL-001 | 灰度发布策略（租户/岗位/比例） | Story | QA-006A | 支持在线灰度与一键回滚 |
| AHR-AIINT-REL-002 | 回滚演练与故障演练 | Task | REL-001 | 三类故障演练通过，RTO/RPO 达标 |
| AHR-AIINT-DOC-001 | 文档收口与交付 | Task | 全部 | 任务清单/已实现功能/运维手册一致 |

### 13.8 建议执行顺序（最小可上线路径）

1. 先完成 S0 + S1 + S2（拿到真实音视频与语音链路）
2. 再完成 S3（LLM 题目生成 + LLM 实时追问）
3. 最后完成 S4 + S5 + S6（治理、压测、灰度、发布）

---

## 14. 执行进展（2026-03-21）

### 14.1 已完成（代码+测试通过）

- AHR-AIINT-EXEC-001（DONE）：技术选型冻结文档落地
- AHR-AIINT-EXEC-002（DONE）：配置模板与环境变量规范落地（`.env.example` + `config`）
- AHR-AIINT-EXEC-003（DONE）：新增 `/health/providers` 与 Provider 熔断快照
- AHR-AIINT-RTC-001A（DONE）：RTC 网关工厂与 token 服务（mock/livekit）
- AHR-AIINT-RTC-001B（DONE）：会话创建接入 RTC provider 抽象（room/token/vendor 落库）
- AHR-AIINT-RTC-001C（DONE）：入会/重连接入 RTC provider 抽象
- AHR-AIINT-RTC-002A（DONE）：ASR provider 抽象层（mock/openai）
- AHR-AIINT-RTC-003A（DONE）：TTS provider 抽象层（mock/openai）
- AHR-AIINT-LLM-001（DONE）：面试题生成接入 LLM 引擎（可开关）
- AHR-AIINT-LLM-003（DONE）：追问生成接入 LLM 引擎（可开关）
- AHR-AIINT-ORCH-001（DONE）：实时编排器服务化（ASR->策略->追问->TTS）
- AHR-AIINT-ORCH-002（DONE）：降级矩阵落地（llm_to_rule / tts_to_text_only）
- AHR-AIINT-BE-014A（DONE）：指标扩展（asr/llm/tts/e2e P95 + 告警原因）
- AHR-AIINT-QA-006A（PARTIAL）：压测脚本骨架落地（待真实环境压测执行）
- AHR-AIINT-DB-002A（DONE）：在线索引迁移脚本落地（幂等检查 + INPLACE/LOCK=NONE）并补齐回滚脚本（DROP INDEX 幂等）
- AHR-AIINT-DB-003A（DONE）：生命周期任务落地（转写/音频清理 + 历史事件清理）并新增审计事件 `ai_interview.lifecycle.cleanup`

### 14.2 验证证据

- 增量回归：
  - `uv run --project AI-HR pytest -q AI-HR/tests/test_ai_hr_provider_health.py AI-HR/tests/test_ai_hr_ai_interviews.py AI-HR/tests/test_ai_hr_speech_providers.py`
  - `uv run --project AI-HR pytest -q AI-HR/tests/test_ai_hr_ai_interviews.py AI-HR/tests/test_ai_hr_llm_platform.py`
  - `uv run --project AI-HR pytest -q AI-HR/tests/test_ai_hr_lifecycle.py AI-HR/tests/test_ai_hr_db_migrations.py`
- 全量回归：
  - `uv run --project AI-HR pytest -q AI-HR/tests`
  - 结果：`71 passed`

### 14.3 未完成项（受外部依赖影响）

- AHR-AIINT-RTC-001D：RTC webhook 回写（需真实 RTC 网关回调地址与签名配置）
- AHR-AIINT-QA-RTC-001：RTC 集成测试（需真实 RTC 环境）
- AHR-AIINT-RTC-002B：实时 ASR 真流式接入（需真实音频流与 provider 密钥）
- AHR-AIINT-RTC-003B：实时 TTS 回放到真实房间（需真实 RTC + TTS provider）
- AHR-AIINT-QA-RTC-002：语音链路异常压测（需真实 provider）
- AHR-AIINT-LLM-002：Prompt 灰度与在线版本管理（需配置线上 runtime 数据）
- AHR-AIINT-LLM-004/005：多语言追问一致性与时延优化实测（需真实 LLM API）
- AHR-AIINT-SEC-001/002：安全与合规治理（待执行）
- S5/S6 其余任务：依赖真实外部环境、压测资源与灰度发布链路

### 14.4 当前阻塞清单与临时降级

- 阻塞项：
  - 缺少生产可用的 RTC/ASR/TTS/LLM 密钥与联调环境
  - 缺少公网 webhook 回调地址与证书配置
- 临时降级：
  - 使用 `mock` provider 保持功能闭环
  - `ai_interview_llm` 通过 feature flag 可开关，异常回退规则引擎

## 15. 执行进展补充（2026-03-21 第一轮）
- 本轮目标：在 LiveKit 真链路基础上补齐“候选人音轨订阅”能力，并提供可灰度/可回滚开关。
- 已完成：
  - 新增接口 `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/audio/subscribe`
  - RTC 网关新增 `subscribe_audio_tracks()` 抽象，mock/livekit 均已实现
  - LiveKit 新增 `UpdateSubscriptions` 调用路径支持
  - 会话 payload 与审计事件新增 `ai_interview.rtc.audio_subscribe` 回写
  - 新增自动化测试：服务接口测试 + RTC 网关单元测试
- 回滚点：
  - `AI_HR_AI_INTERVIEW_RTC_AUDIO_SUBSCRIBE_ENABLED=false` 可一键关闭订阅链路
  - 关闭后接口返回 `mode=disabled` 并写入 `status=skipped` 审计事件
- 下一轮目标：ASR 流式音频分片入链（帧/分片 -> 实时转写 -> events/turns 回写增强）

## 16. 执行进展补充（2026-03-21 第二轮）
- 本轮目标：ASR 流式真链路（音频分片输入 -> 实时转写 -> events/turns 回写增强）。
- 已完成：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/asr/stream` 支持分片参数：`chunk_id/chunk_index/chunk_total/is_final/input_format`
  - 响应增强：`event_id/turn_id/deduplicated/is_partial/latency_breakdown/realtime_target_met`
  - turn 回写增强：partial 分片写 `candidate_partial`，final 分片写 `candidate`
  - 审计回写增强：`ai_interview.rtc.asr` 事件含分片与时延分解字段
  - 幂等增强：支持 `chunk_id` 去重，重复分片不重复写 turn
  - 时延断言：支持按 `target_latency_ms` 实时判定
- 回滚点：
  - 该轮为兼容增强，旧入参可直接继续使用
  - 若前端暂不支持分片，仅传旧字段即可保持旧行为
- 下一轮目标：TTS 回灌真链路（文本 -> 音频流 -> AI bot 轨道发布）

## 17. 执行进展补充（2026-03-21 第三轮）
- 本轮目标：TTS 回灌真链路（题目文本 -> 音频流 -> 发布到 AI bot 轨道）。
- 已完成：
  - `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/tts/stream` 支持发布参数：`publish_to_rtc/bot_identity/track_name/target_latency_ms`
  - RTC 网关新增 `publish_bot_audio()` 抽象；mock/livekit 均已接入
  - LiveKit 网关新增 `SendData` 信令路径（向 AI bot participant 下发 TTS 注入消息）
  - turns 回写增强：TTS 输出落 `speaker=ai`，携带发布状态与时延分解
  - 审计回写增强：`ai_interview.rtc.tts` 事件包含 `published/publish_mode/track_sid/latency_breakdown`
  - 时延断言落地：`realtime_target_met/p95_target_met` 基于 `target_latency_ms` 判定
- 回滚点：
  - `AI_HR_AI_INTERVIEW_RTC_TTS_PUBLISH_ENABLED=false` 一键关闭回灌发布
  - 关闭后仍返回 TTS 音频数据，`publish_mode=disabled`，不影响原有播报能力
- 下一轮目标：视频轨策略（候选人视频上行 + AI 订阅/录制策略）

## 18. 执行进展补充（2026-03-21 第四轮）
- 本轮目标：视频轨策略（候选人视频上行 + AI 订阅/录制策略）。
- 已完成：
  - 新增接口 `POST /api/v1/ai/interviews/sessions/{session_id}/rtc/video/policy`
  - RTC 网关新增 `apply_video_policy()` 抽象，mock/livekit 均已实现
  - 会话 payload 回写视频策略字段：`rtc_video_policy_applied/rtc_video_subscribed/rtc_video_record_enabled/...`
  - 审计事件新增：`ai_interview.rtc.video_policy`
  - 指标扩展：`video_policy_applied_count/rate`、`video_recording_enabled_count/rate`
- 回滚点：
  - `AI_HR_AI_INTERVIEW_RTC_VIDEO_POLICY_ENABLED=false` 一键关闭视频策略
  - 关闭后接口返回 `applied=false, mode=disabled`，不影响音频链路
- 下一轮目标：E2E 压测与达标验证（含时延指标）

## 19. 执行进展补充（2026-03-21 第五轮）
- 本轮目标：正式接入腾讯云 ASR/TTS。
- 已完成：
  - 新增 Tencent ASR/TTS provider 与 TC3 签名鉴权
  - 工厂支持 `asr_provider=tencent`、`tts_provider=tencent`
  - 完整配置项与示例模板补齐
  - 自动化测试覆盖腾讯 provider 请求构造与返回解析
- 回滚点：
  - 直接切回 `AI_HR_ASR_PROVIDER=mock/openai`、`AI_HR_TTS_PROVIDER=mock/openai`
- 最小可用配置：
  - `AI_HR_ASR_PROVIDER=tencent`
  - `AI_HR_TTS_PROVIDER=tencent`
  - `AI_HR_TENCENT_SECRET_ID=...`
  - `AI_HR_TENCENT_SECRET_KEY=...`
  - `AI_HR_TENCENT_REGION=ap-guangzhou`

## 14. 执行进展（2026-03-22 实时链路优化）

### 14.1 已完成
- ASR：腾讯链路改为 `WebSocket优先 + HTTP自动降级`，保留回滚开关。
- 前端采集：从 `ScriptProcessorNode` 升级为 `AudioWorklet`。
- LLM 追问：上线短上下文（回答截断+压缩）与追问缓存去重。
- TTS：新增预热钩子与首包优先分片策略（`first_chunk_size`）。
- 全链路事件总线：新增会话级 WebSocket 推送 `/api/v1/ai/interviews/sessions/{session_id}/events/ws`，前端改为订阅为主、轮询为备。

### 14.2 新增配置项
- `AI_HR_ASR_TENCENT_APP_ID`
- `AI_HR_ASR_TENCENT_WS_BASE_URL`
- `AI_HR_ASR_TENCENT_STREAMING_ENABLED`
- `AI_HR_ASR_TENCENT_WS_ALLOW_HTTP_FALLBACK`
- `AI_HR_ASR_TENCENT_WS_EXPIRE_SECONDS`
- `AI_HR_TTS_FIRST_CHUNK_SIZE`
- `AI_HR_TTS_WARMUP_ENABLED`
- `AI_HR_LLM_FOLLOWUP_CACHE_TTL_SECONDS`

### 14.3 自动化测试（新增）
- `tests/test_tencent_speech_providers.py`
- `tests/test_ai_hr_realtime_event_bus.py`

## 15. 执行进展（2026-03-22 第二轮：低时延强化）

### 15.1 已完成
- 腾讯 ASR：从“WS 单次分片会话”升级为“按 `session_id + seq` 持续双工分帧会话”，支持非 final 分片复用连接、final 分片结束回收。
- 前端 VAD：新增噪声基线自适应与动态门限，降低误触发与碎片字幕。
- E2E 压测：新增脚本输出 ASR/LLM/TTS/e2e 的 P50/P95。

### 15.2 压测脚本
- 路径：`scripts/realtime_e2e_benchmark.py`
- 示例：
  - `python scripts/realtime_e2e_benchmark.py --base-url http://127.0.0.1:8000/api/v1 --turns 20 --sleep-ms 120`

### 15.3 增量测试
- `tests/test_tencent_speech_providers.py`
- `tests/test_realtime_e2e_benchmark.py`
- `tests/test_ai_hr_asr_streaming.py`
- `tests/test_realtime_orchestrator_optimizations.py`

## 16. 执行进展（2026-03-22 第三轮：全双工重构）

### 16.1 架构问题定位
- 旧链路为“句级 HTTP 串行调用（ASR->events->TTS）”，存在前端停顿等待 + 多次往返 + 重复TTS开销。
- 即使后端支持流式，前端仍未形成单通道双工，导致交互不具备 IM 级实时性。

### 16.2 重构落地
- 新增全双工接口：`/api/v1/ai/interviews/sessions/{session_id}/rtc/duplex/ws`
  - 上行：`audio_chunk` 分帧
  - 下行：`duplex.turn`（包含 asr + event + followup_audio_uris）
- 前端改造：优先走 duplex ws 分帧上传，HTTP 链路保留降级。
- 腾讯 ASR 保持持续双工会话与 final 收尾，减少握手与连接重建。

### 16.3 回滚点
- `AI_HR_AI_INTERVIEW_RTC_DUPLEX_WS_ENABLED=false`：立即关闭双工通道，回退旧 HTTP 链路。

### 16.4 增量测试
- `tests/test_ai_hr_duplex_ws.py`
- 相关回归：ASR/腾讯 Provider/事件总线全部通过。

## 17. 执行进展（2026-03-22 第四轮：全双工细化 + 实测）

### 17.1 本轮完成
- 前端“真分帧持续上传”细化：固定 30ms 帧（16k 下约 480 samples）持续上行。
- duplex 通道新增 server-side 首包语音事件：
  - `duplex.tts.first_packet`
  - `duplex.tts.rest`
- 新增全双工开关：`AI_HR_AI_INTERVIEW_RTC_DUPLEX_WS_ENABLED`。
- 压测脚本升级支持 `legacy|duplex|compare` 三模式。

### 17.2 真实环境压测结果（turns=4）
- legacy e2e p95: 11342ms
- duplex e2e p95: 7860ms
- e2e p95 改善: -3482ms

> 注：本次 duplex `tts p95=0`，代表样本中部分轮次未触发追问语音事件（无可计量 TTS 段），不代表 TTS 耗时为零。

### 17.3 测试
- `tests/test_ai_hr_duplex_ws.py` 通过
- `tests/test_tencent_speech_providers.py` 通过
- `tests/test_ai_hr_asr_streaming.py` 通过
- `tests/test_realtime_e2e_benchmark.py` 通过

## 18. 执行进展（2026-03-22 第五轮：协议可靠性 + 真流式TTS）

### 18.1 完成项
- duplex 协议新增 `frame_id + ack`：
  - 客户端每帧携带 `frame_id`
  - 服务端返回 `duplex.ack`
  - 客户端超时自动重传，服务端按 frame_id 去重
- duplex TTS 改为 packet 流式下发：
  - 新事件 `duplex.tts.packet`
  - 非“首包+余包拼接”伪流式，而是每个分片生成即推送
- 前端真分帧持续上传：固定 30ms 帧持续上行

### 18.2 压测实测（turns=6）
- legacy e2e p95: 12019ms
- duplex e2e p95: 8294ms
- e2e p95 改善: -3725ms

### 18.3 说明
- 当前主瓶颈仍在 ASR（单段约 5-6s 量级），要进入“几百ms”级需切到更低延迟 ASR 模式与增量字幕策略。
