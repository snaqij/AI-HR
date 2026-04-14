# 实时语音面试统一编排 Jira 任务拆分版 v1

## 文档目标

本任务拆分版用于将《实时语音面试统一编排实施清单 v1》落地为可执行的 Jira 任务。

适用范围：

- `AI-HR/ai_hr/services/interview_runtime/*`
- `AI-HR/ai_hr/services/ai_interviews.py`
- `AI-HR/ai_hr/services/llm/prompts.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/*`

目标：

- 统一 `ai_hr` 与 `ten_agent` 的面试编排主逻辑
- 解决自我介绍阶段无限追问
- 让题库驱动、状态机推进、实时执行分层清晰
- 为后续 ASR 容错与单主题深挖控制打基础

---

## Epic 1：统一运行时编排主逻辑

### Story 1.1：扩展阶段策略定义，支持统一推进规则

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/flow_policy.py`

**改造目标**

扩展 `StagePolicy`，让阶段策略不仅描述语义，还能指导运行时推进和转场。

**改造内容**

- 为 `StagePolicy` 增加字段：
  - `completion_mode`
  - `hard_max_turns`
  - `allow_deep_dive`
  - `topic_round_limit`
  - `must_exit_on_followup_limit`
- 为 `S2/S3/S4+` 配置不同推进策略
- 新增 helper：
  - `get_stage_hard_turn_limit(stage_code)`
  - `get_stage_topic_round_limit(stage_code)`
  - `is_stage_deep_dive_allowed(stage_code)`

**验收标准**

- `S2` 最多补问 1 次
- `S3` 最多补问 2 次
- `S4/S5/S6` 单主题最多追问 3 轮
- 运行时可以从 `StagePolicy` 中读取硬边界，不再依赖散落的硬编码

**风险**

- 现有 `StagePolicy` 消费方可能依赖旧字段结构

**依赖**

- 无

---

### Story 1.2：统一 QuestionFlowEngine，让 S2/S3 进入标准题目推进

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`

**改造目标**

取消 `S1/S2/S3` 对统一题目推进逻辑的豁免，让所有阶段都由同一套状态机推进。

**改造内容**

- 修改 `init_state()`，新增以下状态字段：
  - `stage_turn_count`
  - `question_completion_reason`
  - `focus_experience`
  - `focus_module`
  - `active_question_type`
  - `active_topic_name`
  - `active_topic_rounds`
  - `candidate_requested_move_on`
  - `profile_collected`
- 修改 `apply_turn_result()`：
  - 去掉 `S1/S2/S3` early return
  - 所有阶段统一消费 `followup_count_current`
  - 支持新的完成原因
- 支持以下新输入：
  - `stage_progress_completed`
  - `candidate_requested_move_on`
  - `stage_turn_limit_reached`
  - `topic_round_limit_reached`

**验收标准**

- `S2/S3` 可以正常推进 `active_question_index`
- 当前题达到追问上限时必须结束
- `candidate_requested_move_on=True` 时当前题直接结束
- state 中能记录 `question_completion_reason`

**风险**

- `ai_interviews.py` 当前也调用该引擎，可能行为发生变化

**依赖**

- Story 1.1

---

### Story 1.3：收缩 StageProgressEngine 的职责，避免阶段卡死

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/stage_progress.py`

**改造目标**

让 `StageProgressEngine` 回归“证据采集器”角色，不再成为无限追问的实际触发器。

**改造内容**

- 调整 `S2` 完成标准：
  - 从“尽量采满”改为“画像最小集达成即可推进”
- 调整 `S3` 完成标准：
  - 不再要求强 `jd_hits` 才能离场
  - 聚焦主项目、主模块、真实使用证据
- 优化 `reason` 输出，方便运行时引擎消费

**验收标准**

- 自我介绍阶段拿到“最近经历 + 项目锚点 + 角色”后可推进
- 技术栈阶段拿到“主技术 + 使用证据”后可推进
- 不再因信号不完美而长时间停留在 `S2/S3`

**风险**

- 完成条件放松后，可能导致画像信息采集不完整

**依赖**

- Story 1.2

---

### Story 1.4：新增统一 runtime engine 作为共享编排入口

**类型**

- Story

**涉及文件**

- 新增 `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`

**改造目标**

在 `ai_hr` 内建立唯一编排入口，后续 `ai_interviews.py` 和 `ten_agent` 都通过该引擎处理候选人轮次。

**改造内容**

- 新增：
  - `init_runtime_state(question_pack)`
  - `process_candidate_turn(...)`
- 引擎内部统一调用：
  - `evaluate_answer()`
  - `StageProgressEngine.update()`
  - `QuestionFlowEngine.apply_turn_result()`
  - `StagePolicy` helpers
- 输出统一编排结果：
  - `updated_state`
  - `next_action`
  - `must_transition`
  - `flow_reason`
  - `current_question`

**验收标准**

- 可通过统一函数输入 turn，得到结构化 flow decision
- 不依赖 `ten_agent` 的本地编排逻辑也能完成推进判断

**风险**

- 若输出 contract 设计不稳，后续接入方容易反复改

**依赖**

- Story 1.1
- Story 1.2
- Story 1.3

---

## Epic 2：统一题库结构与阶段问题骨架

### Story 2.1：统一 question pack schema，新增 question_type

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/ai_interviews.py`

**改造目标**

统一题目结构，使 `ai_hr` 和 `ten_agent` 使用同一 question schema。

**改造内容**

- 修改 `_normalize_question_item()`
- 在 question item 中新增：
  - `question_type`
- 约定取值：
  - `profile`
  - `capability`
  - `wrap_up`
- 阶段映射建议：
  - `S2/S3 -> profile`
  - `S4/S5/S6 -> capability`
  - `S7/S8 -> wrap_up`

**验收标准**

- 所有规范化后的 question item 均带 `question_type`
- 老 question item 缺失时能兼容补默认值

**风险**

- 老缓存 question pack 不包含该字段

**依赖**

- 无

---

### Story 2.2：重排种子题顺序，避免自我介绍后直接深挖项目

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/ai_interviews.py`

**改造目标**

将种子题重排为“画像补全 -> 主线确认 -> 正式能力题”，避免自我介绍后直接进入技术深挖。

**改造内容**

- 修改 `_build_stage_seed_questions()`
- 新的顺序建议：
  - `S2` 自我介绍
  - `S3` 最近经历确认
  - `S3` 主项目确认
  - `S3` 主模块确认
  - `S3` 真实使用确认
  - `S4` 单主题项目深挖
  - `S5` JD 匹配
  - `S6` 排障/工程能力
  - `S7` 公司反问

**验收标准**

- 自我介绍后不会立即出现“最难技术点是什么”式问题
- 题目覆盖路径更符合面试节奏

**风险**

- 新题顺序可能影响当前已有预构建 question pack 的评估对比结果

**依赖**

- Story 2.1

---

### Story 2.3：统一 `ten_agent` 的 fallback 题库来源

**类型**

- Story

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造目标**

移除 `ten_agent` 本地手写 3 题兜底逻辑，改为复用 `ai_hr` 的统一种子题生成逻辑。

**改造内容**

- 替换本地 fallback question pack
- 改为：
  - 调统一种子题 builder
  - 或加载统一规范化 question pack

**验收标准**

- `ten_agent` 不再维护与 `ai_hr` 不一致的手写 fallback 题库
- fallback 行为和主逻辑一致

**风险**

- `ten_agent` 初始化阶段可能需要引入更多依赖

**依赖**

- Story 2.1
- Story 2.2

---

## Epic 3：统一 `ten_agent` 的实时执行入口

### Story 3.1：缩小 `_handle_interaction()` 职责，改为消费 runtime engine 输出

**类型**

- Story

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造目标**

让 `main.py` 中的 `_handle_interaction()` 只做实时执行，不再本地决定题目推进和阶段切换。

**改造内容**

- 在 `_handle_interaction()` 中接入共享 `runtime_engine.process_candidate_turn(...)`
- 由 runtime engine 返回：
  - `updated_state`
  - `next_action`
  - `must_transition`
  - `current_question`
  - `flow_reason`
- `_handle_interaction()` 仅负责：
  - 调用共享引擎
  - 构造 prompt
  - 启动 LLM streaming
  - 输出 TTS

**验收标准**

- `main.py` 中不再本地拍板 `S2 -> S3 -> S4`
- 阶段推进由共享 runtime engine 返回

**风险**

- 迁移过程中可能出现旧逻辑与新逻辑并存冲突

**依赖**

- Epic 1 全部 Story

---

### Story 3.2：删除 `ten_agent` 本地阶段推进硬编码

**类型**

- Story

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造目标**

删除当前 `main.py` 中依赖 `was_satisfied / stage_signals_completed` 的本地阶段推进硬编码。

**改造内容**

- 删除或弱化以下本地逻辑：
  - `was_satisfied` 直接触发阶段切换
  - `stage_signals_completed` 直接触发阶段切换
  - `SELF_INTRO -> TECH_STACK`
  - `TECH_STACK -> PROJECT_DEEP_DIVE`
- 改为依赖共享 runtime engine 的 `next_action`

**验收标准**

- `main.py` 不再作为第二套阶段状态机
- 所有推进都来自共享编排结果

**风险**

- 若 runtime engine contract 不完整，可能临时需要保留少量兼容逻辑

**依赖**

- Story 3.1

---

### Story 3.3：统一 SessionContext 语义，增加主题与实体状态

**类型**

- Story

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/session_context.py`

**改造目标**

让实时会话上下文不仅记录最近轮次，还能记录主项目、主模块和当前主题状态。

**改造内容**

- 为 `SessionContext` 增加：
  - `focus_experience`
  - `focus_module`
  - `known_entities`
  - `entity_aliases`
  - `active_topic_name`
  - `active_topic_rounds`

**验收标准**

- 同一项目的别名可归一
- 当前主题能持续跟踪

**风险**

- 上下文结构变复杂，需注意序列化兼容

**依赖**

- Story 3.1

---

## Epic 4：增强 Prompt 约束与 ASR 容错

### Story 4.1：扩展 PromptBuildInput，支持 question_type / topic / transition 语义

**类型**

- Story

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/prompt_builder.py`

**改造目标**

让 prompt 构造层能感知当前是在补画像还是在正式评估，以及当前是否必须收口和转场。

**改造内容**

- `PromptBuildInput` 新增：
  - `question_type`
  - `focus_experience`
  - `focus_module`
  - `active_topic_name`
  - `active_topic_rounds`
  - `must_transition`
  - `candidate_requested_move_on`

**验收标准**

- prompt 能明确区分“画像题”和“能力题”
- prompt 能明确知道当前是否必须转场

**风险**

- prompt 输入过多可能让模板过重

**依赖**

- Story 2.1
- Story 3.1

---

### Story 4.2：重写阶段指令，加入阶段禁止项与转场规则

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/llm/prompts.py`

**改造目标**

通过 prompt 明确限制 `S2/S3` 的问法边界，并强化 `S4+` 的单主题深挖规则。

**改造内容**

- 修改 `build_interview_stage_instruction()`
- `S2` 明确：
  - 只问背景、经历、角色
  - 不允许进入 API、参数、实现细节
  - 满足最小画像后必须收口
- `S3` 明确：
  - 只确认主项目、主模块和真实使用
  - 不允许过深实现追问
  - 达到边界必须转场
- `S4+` 明确：
  - 一次只围绕一个主题
  - 单主题最多 3 轮
  - 候选人连续答不上来要换题

**验收标准**

- 自我介绍阶段不再出现底层实现细节追问
- Prompt 与状态机边界一致

**风险**

- prompt 改动可能影响回复风格，需要观察 TTS 体验

**依赖**

- Story 4.1

---

### Story 4.3：新增 transcript normalizer，统一处理 ASR 错词

**类型**

- Story

**涉及文件**

- 新增 `AI-HR/ai_hr/services/interview_runtime/transcript_normalizer.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造目标**

将 ASR 文本视为带噪声输入，先做语义归一，再进入 prompt 构造和追问。

**改造内容**

- 新增 transcript normalization 能力
- 输入：
  - 原始 transcript
  - 当前 stage
  - 当前 question
  - recent history
  - known entities
- 输出：
  - `normalized_transcript`
  - `resolved_entities`
  - `uncertain_terms`
  - `semantic_hints`

**验收标准**

- `AIHR / AIH / AIPR` 不被视为多个项目
- `TTS / TDS` 不再触发无意义澄清
- `Date / data` 等错词不会持续带偏追问

**风险**

- 过度纠偏可能误解候选人真实意思

**依赖**

- Story 3.3

---

## Epic 5：增强单主题深挖与换题控制

### Story 5.1：引入 topic state，限制单主题追问轮数

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/session_context.py`

**改造目标**

避免在同一项目里无边界跳主题和死磕一个细节点。

**改造内容**

- 增加 topic state：
  - `active_topic_name`
  - `active_topic_rounds`
  - `active_topic_status`
- 规则：
  - 一个题只绑定一个 topic
  - 单 topic 最多 3 轮
  - topic exhausted 后必须切题

**验收标准**

- 不再出现 WebSocket -> TTS -> Date -> Redis TTL 乱跳式追问
- 单个主题有明确边界

**风险**

- topic 边界识别需要和 question/state 对齐

**依赖**

- Story 3.3
- Story 4.1

---

### Story 5.2：候选人“继续吧 / 不清楚”触发当前主题结束

**类型**

- Story

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`
- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改造目标**

把候选人主动放弃当前点位视为明确的换题信号。

**改造内容**

- 识别：
  - “继续吧”
  - “不清楚”
  - “没考虑过”
  - “换个话题”
- runtime engine 接收到该信号后：
  - 标记 `candidate_requested_move_on=True`
  - 当前题记为 `completed_with_gap`
  - 进入下一题或下一阶段

**验收标准**

- 候选人明确放弃后，系统不会继续围绕当前点死磕

**风险**

- 某些口语化表达可能被误判为放弃信号

**依赖**

- Story 1.4

---

## 建议实施顺序

### Sprint 1

- Story 1.1
- Story 1.2
- Story 1.3
- Story 1.4

目标：
先立统一编排骨架。

### Sprint 2

- Story 2.1
- Story 2.2
- Story 2.3
- Story 3.1
- Story 3.2

目标：
统一题库和 `ten_agent` 接入方式。

### Sprint 3

- Story 3.3
- Story 4.1
- Story 4.2
- Story 4.3
- Story 5.1
- Story 5.2

目标：
增强实时稳定性、ASR 容错和单主题控制。

---

## 最终验收口径

改造完成后，应满足：

- 自我介绍后先补全候选人画像，而不是立刻深挖
- 所有阶段由统一状态机推进
- `ten_agent` 不再维护第二套编排主逻辑
- 题库由 `ai_hr` 统一生成与规范化
- 每题有限追问
- 候选人答不上来或要求继续时能够自然转场
- ASR 错词不会持续带偏提问
- 面试能够覆盖多个能力面，而不是困死在一个项目点

