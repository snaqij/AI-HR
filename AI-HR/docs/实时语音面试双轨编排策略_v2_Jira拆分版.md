# 实时语音面试双轨编排策略 v2 - Jira 拆分版

## 文档目标

把“开发任务拆分版 v2”转换为可直接录入 Jira 的 Epic / Story / 验收标准格式，便于排期、分工和跟踪。

---

## Epic 1

### 统一运行时输入源

### 目标

- 让 `question_pack` 成为实时面试唯一主题源
- 让 `company_info` 成为公司介绍唯一资料源
- 让 `ten_agent` 优先消费 `ai_hr` 注入内容

### Story 1.1

#### 在 `ai_hr` 侧装配完整运行时题包与公司信息

**涉及文件**

- `AI-HR/ai_hr/services/ai_interviews.py`

**改动内容**

- 在 session 创建 / 启动 / TEN prepare 之前，装配：
  - `question_pack`
  - `question_pack_source`
  - `question_pack_version`
  - `company_info`
  - `company_info_source`
  - `company_info_version`

**验收标准**

- session runtime payload 中可拿到完整题包与公司资料
- 缺少显式公司信息时，可使用 `data/company_info.txt` 作为 dev fallback

**风险**

- 历史 session 无题包时仍需兼容 fallback

---

### Story 1.2

#### 在 TEN property 中正式注入题包和公司资料

**涉及文件**

- `AI-HR/ai_hr/services/ten_runtime.py`

**改动内容**

- 在 `interview_orchestrator` property 中增加：
  - `question_pack`
  - `question_pack_source`
  - `question_pack_version`
  - `company_info`
  - `company_info_source`
  - `company_info_version`

**验收标准**

- 生成的 TEN property 文件中可见上述字段
- 值与 `ai_hr` session payload 保持一致

**风险**

- property 文件体积增大

---

### Story 1.3

#### ten_agent 优先消费注入题包和公司信息

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`
- `AI-HR/ai_hr/services/interview_runtime/question_schema.py`

**改动内容**

- `on_init()` 题包加载优先级改为：
  1. runtime 注入题包
  2. 本地文件
  3. seed fallback
- 启动时校验并记录 `company_info`
- 题包统一走 `normalize_question_pack()`

**验收标准**

- 日志中明确显示 `question_pack_loaded_from=ai_hr_runtime`
- 实时面试首问顺序与预生成题包一致

**风险**

- 旧题包结构不兼容时可能触发归一化异常

---

## Epic 2

### 统一阶段推进与题目切换决策

### 目标

- 由共享 runtime 决策层统一控制“问什么、追不追、何时切题、何时切阶段”
- 避免 `main.py` 本地重复判断

### Story 2.1

#### 扩展 `RuntimeTurnDecision`

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`

**改动内容**

- 新增字段：
  - `output_mode`
  - `target_question`
  - `must_transition`
  - `transition_brief`
  - `followup_budget_remaining`
  - `defer_company_qa`

**验收标准**

- 决策层能明确返回：
  - 当前应播主问题
  - 还是应走追问
  - 是否应该切下一题

**风险**

- ten_agent 对旧 contract 的消费逻辑需要同步更新

---

### Story 2.2

#### 显式化题目状态流转

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`

**改动内容**

- state 增加：
  - `current_question_id`
  - `current_question_status`
  - `current_question_asked`
  - `current_output_mode`
  - `state_version`
- 状态固定为：
  - `pending`
  - `scripted_asked`
  - `followup_active`
  - `completed`

**验收标准**

- 题目只在完成时推进 `active_question_index`
- 不再因一次追问就错误切题

**风险**

- 与已有 `derive_stage()` 兼容性需要验证

---

### Story 2.3

#### 固化阶段边界与 S2 退出规则

**涉及文件**

- `AI-HR/ai_hr/services/interview_runtime/flow_policy.py`
- `AI-HR/ai_hr/services/interview_runtime/runtime_engine.py`
- `AI-HR/ai_hr/services/interview_runtime/question_flow.py`

**改动内容**

- 明确：
  - `S1` 开场
  - `S2` 自我介绍与画像锚定
  - `S3-S6` 技术题正式推进
  - `S7` 公司介绍与候选人反问
  - `S8` 收尾
- `S2` 不允许长时间深挖

**验收标准**

- `S2` 可稳定退出到 `S3`
- `S3-S6` 技术题能逐题推进

**风险**

- 与 `StageProgressEngine` 的边界需重新梳理

---

## Epic 3

### 主问题直出，LLM 只追问

### 目标

- 主问题直接使用题库原题
- LLM 只负责短追问
- 不再由 LLM 改写主干问题

### Story 3.1

#### 在 ten_agent 中引入 scripted question 分支

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改动内容**

- `_handle_interaction()` 按 `output_mode` 分支：
  - `scripted_question`
  - `llm_followup`
- 新增：
  - `_emit_scripted_question(...)`
  - `_run_llm_followup(...)`
  - `_normalize_candidate_transcript(...)`

**验收标准**

- `S3-S6` 首问不等待 LLM
- 主问题内容与题库原题一致

**风险**

- TTS 事件时序与 question buffer 需要重新对齐

---

### Story 3.2

#### 收紧 follow-up prompt 权限

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/prompt_builder.py`
- `AI-HR/ai_hr/services/llm/prompts.py`

**改动内容**

- `PromptBuildInput` 增加：
  - `output_mode`
  - `target_question_id`
  - `followup_budget_remaining`
- follow-up prompt 明确：
  - 不重述主问题
  - 不改写题库原题
  - 只允许一条短追问

**验收标准**

- follow-up 明显变短
- 不再出现 LLM 重写主问题

**风险**

- 约束过紧可能影响追问自然度

---

### Story 3.3

#### 稳定记录 scripted question 与 follow-up 上下文

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/session_context.py`

**改动内容**

- 增加：
  - `current_scripted_question_id`
  - `current_scripted_question_text`
  - `last_followup_text`

**验收标准**

- 历史上下文中能清楚区分主问题和追问
- prompt 不再因上下文混乱而重复问题

**风险**

- 需兼容现有 recent turns 逻辑

---

## Epic 4

### 公司信息严格资料化，且只在尾段回答

### 目标

- 中途公司问题不打断主线
- 公司介绍只在 `S7` 发生
- 回答只能基于 `company_info`

### Story 4.1

#### 中途公司问题统一做延后提示

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`

**改动内容**

- 增加 `_is_company_question(...)`
- 增加 `_emit_company_qa_defer_reply(...)`
- 在 `S1-S6` 命中公司类问题时：
  - 不切 `S7`
  - 不记录问题
  - 不调用自由 LLM
  - 固定回复“最后统一介绍”

**验收标准**

- 候选人中途问“你们公司做什么”时，不会得到随机公司介绍
- 当前技术主线不被打断

**风险**

- 关键词规则过窄会漏识别

---

### Story 4.2

#### `S7 COMPANY_QA` 严格基于公司资料回答

**涉及文件**

- `AI-HR/ten_agent/ten_packages/extension/interview_orchestrator_python/main.py`
- `AI-HR/ai_hr/services/llm/prompts.py`

**改动内容**

- `S7` 第一轮必须基于 `company_info`
- company QA prompt 增加硬约束：
  - 不得编造公司名称、业务、团队、岗位、福利
  - 资料未提供则明确说明

**验收标准**

- 多次测试公司介绍内容稳定一致
- 不再出现资料外公司名或业务描述

**风险**

- `company_info` 为空时需要明确 fallback 响应策略

---

## Epic 5

### 验证与回归

### 目标

- 为新的双轨编排主链路建立最小可回归保障

### Story 5.1

#### 注入链路与 property 测试

**涉及文件**

- `AI-HR/tests/test_ai_hr_ai_interviews.py`
- `AI-HR/tests/test_ten_runtime_payload.py`

**验收标准**

- `question_pack` 和 `company_info` 均已进入 runtime property

---

### Story 5.2

#### question flow / runtime decision 测试

**涉及文件**

- `AI-HR/tests/test_ai_hr_ai_interviews_question_flow.py`
- `AI-HR/tests/test_interview_runtime_dual_track.py`

**验收标准**

- 当前题未播时返回 `scripted_question`
- 回答不足时返回 `llm_followup`
- 到达预算后切下一题
- `S2` 能稳定进入 `S3`

---

### Story 5.3

#### company QA 行为测试

**涉及文件**

- `AI-HR/tests/test_interview_runtime_dual_track.py`

**验收标准**

- `S1-S6` 中途公司提问只返回延后话术
- `S7` 回答严格基于 `company_info`

---

## 推荐迭代顺序

1. Epic 1
2. Epic 2
3. Epic 3
4. Epic 4
5. Epic 5

---

## 里程碑建议

### 里程碑 M1

- 完成 Epic 1
- 结果：
  - ten_agent 正式消费 `ai_hr` 注入题包与公司资料

### 里程碑 M2

- 完成 Epic 2 + Epic 3
- 结果：
  - 主问题直出
  - LLM 只追问
  - 技术题按题库推进

### 里程碑 M3

- 完成 Epic 4 + Epic 5
- 结果：
  - 公司介绍只在尾段稳定回答
  - 整体链路具备回归保障

---

## 一句话总结

Jira 排期上最关键的是先把控制权收口：

- 输入源收口到 `question_pack/company_info`
- 流程收口到 shared runtime
- 文案收口到题库和受限 prompt
- 公司介绍收口到 `S7 + company_info`
