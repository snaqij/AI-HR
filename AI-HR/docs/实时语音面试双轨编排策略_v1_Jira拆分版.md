# 实时语音面试双轨编排策略 v1 - Jira拆分版

## 文档目标

将《实时语音面试双轨编排策略 v1 - 开发任务拆分版》整理为可直接录入 Jira 的任务集合。

适用范围：

- `AI-HR/ai_hr/services/interview_runtime/*`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/*`
- `AI-HR/ai_hr/services/llm/prompts.py`
- `AI-HR/tests/*`

---

## Epic 1：双轨编排核心决策升级

### Story 1.1：扩展 RuntimeTurnDecision，支持输出模式裁决

**目标**

- 让 runtime engine 不仅判断“是否切题”，还判断“下一句是主问题直出还是 LLM 追问”。

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`

**改造内容**

- 为 `RuntimeTurnDecision` 增加：
  - `output_mode`
  - `target_question`
  - `prefetch_question`
  - `should_prefetch_next`
  - `transition_brief`

**验收标准**

- 当前题未播出时返回 `scripted_question`
- 当前题已播且需补问时返回 `llm_followup`
- 当前题结束时返回下一题的 `target_question`

**风险**

- ten_agent 对旧 decision contract 的消费会受影响

---

### Story 1.2：升级 QuestionFlowEngine，显式区分主问题与追问状态

**目标**

- 不再依赖隐式推断题目状态
- 让状态机知道当前题是否已直出、是否处于追问阶段

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`

**改造内容**

- 状态字段增加：
  - `current_question_asked`
  - `current_question_status`
  - `current_output_mode`
  - `state_version`
- 支持状态：
  - `pending`
  - `scripted_asked`
  - `followup_active`
  - `completed`
  - `completed_with_gap`

**验收标准**

- 主问题播出后状态变为 `scripted_asked`
- 追问发生后状态变为 `followup_active`
- 只有题目完成时推进 `active_question_index`

**风险**

- 可能影响现有 `derive_stage()` 与 `apply_turn_result()` 行为

---

### Story 1.3：规范 S2 阶段的“画像锚定”退出规则

**目标**

- 保证 S2 只做主线锁定，不做长时间技术深挖

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`
- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`
- `AI-HR/ai_hr/services/interview_runtime/flow_policy.py`

**改造内容**

- 固定 S2 第一问为 scripted
- 最多允许一次澄清
- 满足画像最小锚点即推进到 S3

**验收标准**

- S2 不会无限停留
- S2 后续问题优先围绕 `focus_experience / focus_module`

**风险**

- 需要与现有 `StageProgressEngine` 行为协调

---

## Epic 2：ten_agent 主问题直出化

### Story 2.1：在 ten_agent 中引入 scripted question 分支

**目标**

- 主问题不再走 LLM 改写，直接播放题库原题

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造内容**

- `_handle_interaction()` 新增分支：
  - `scripted_question`
  - `llm_followup`
- 新增辅助函数：
  - `_emit_scripted_question(...)`
  - `_run_llm_followup(...)`

**验收标准**

- S3-S6 首问不再等待 LLM
- `question.update / question.final` 仍能正常发出

**风险**

- current question buffer 与 pending question 时序可能错位

---

### Story 2.2：保留特殊阶段本地逻辑，但与双轨输出兼容

**目标**

- 不破坏现有 `OPENING / COMPANY_QA / CLOSING` 特殊流程

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造内容**

- 保持 S1/S7/S8 特殊逻辑
- 让这些阶段与 `output_mode` 共存

**验收标准**

- 握手、公司介绍、收尾不回归

**风险**

- 特殊阶段与通用 question flow 之间边界仍可能混杂

---

### Story 2.3：支持下一题预取缓存

**目标**

- 当前题追问时异步准备下一题上下文，降低切题延迟

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/session_context.py`

**改造内容**

- 增加 `prefetch_task`
- 增加 `prefetched_question_*` 缓存字段
- 增加失效判断

**验收标准**

- 当前题结束后，下一题直出速度优于现有模式
- 预取失败不影响主链路

**风险**

- stale cache
- 状态版本不一致

---

## Epic 3：LLM 追问能力收口

### Story 3.1：PromptBuilder 仅服务 follow-up

**目标**

- 明确 LLM 只负责追问，不再改写主问题

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/prompt_builder.py`
- `AI-HR/ai_hr/services/llm/prompts.py`

**改造内容**

- `PromptBuildInput` 增加：
  - `output_mode`
  - `target_question_id`
  - `followup_budget_remaining`
- prompt 约束中加入：
  - 不要复述主问题
  - 不要重写题库原题
  - 只允许一条短追问

**验收标准**

- follow-up 输出明显更短
- 主问题不再被 LLM 换说法

**风险**

- prompt 收太紧后可能影响追问自然度

---

### Story 3.2：引入追问类型分类

**目标**

- 把追问分成澄清型、证据型、取舍型、收束型

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`
- `AI-HR/ai_hr/services/llm/prompts.py`

**改造内容**

- runtime 先判断追问类型
- prompt 根据追问类型约束问法

**验收标准**

- 追问更稳定
- 不再出现长串自由发挥

**风险**

- 分类规则前期可能偏粗，需要迭代

---

## Epic 4：ASR 归一化与结构化上下文增强

### Story 4.1：在 ten_agent 中补 transcript normalizer

**目标**

- 解决技术术语同音误识别带来的无效追问

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/session_context.py`

**改造内容**

- 新增 `_normalize_candidate_transcript(...)`
- 输出：
  - `raw_transcript`
  - `normalized_transcript`

**验收标准**

- `TDS -> TTS`
- `OSSTK -> OSS SDK`
- `威力斯 -> Redis`
- `data -> Date.now`

**风险**

- 规则过强会误修正常语句

---

### Story 4.2：补齐 question schema 结构字段

**目标**

- 保证 question pack 的每题都有统一结构，方便 scripted + prefetch + topic state 共用

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/question_schema.py`
- `AI-HR/ai_hr/services/ai_interviews.py`

**改造内容**

- 强化 question item 补齐：
  - `question_id`
  - `question_type`
  - `topic_name`
  - `topic_aliases`
  - `focus_slot`

**验收标准**

- LLM 生成题和规则题都能补齐结构化字段

**风险**

- 旧缓存 question pack 需要兼容

---

## Epic 5：验证与观测

### Story 5.1：补充双轨编排单元测试

**涉及文件**

- `AI-HR/tests/test_ai_hr_ai_interviews_question_flow.py`
- `AI-HR/tests/test_interview_runtime_dual_track.py`

**验收标准**

- 当前题未播时 -> `scripted_question`
- 当前题已播但回答不足 -> `llm_followup`
- 追问上限达到 -> 直接切题

---

### Story 5.2：补充集成测试与日志点

**涉及文件**

- `AI-HR/tests/test_ai_hr_ai_interviews.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`
- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`

**改造内容**

- 新增日志：
  - `runtime.output_mode_selected`
  - `runtime.scripted_question_emitted`
  - `runtime.llm_followup_triggered`
  - `runtime.prefetch_started`
  - `runtime.prefetch_discarded`
  - `runtime.question_advanced`

**验收标准**

- 可以从日志清楚看出每轮是 scripted 还是 llm
- 可以排查为什么切题或为什么不切题

---

## 推荐交付顺序

1. Epic 1
2. Epic 2
3. Epic 3
4. Epic 4
5. Epic 5

---

## 第一阶段最小闭环

第一阶段建议只交付：

- S3-S6 主问题直出
- LLM 只做追问
- 达到上限直接播下一题

这样能最快验证双轨编排是否成立，同时风险最低。
