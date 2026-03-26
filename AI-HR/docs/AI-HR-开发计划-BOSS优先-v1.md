# AI-HR 开发计划（BOSS 优先，平台可扩展）

## 1. 计划目标
- 基于 `docs/AI-HR-可执行PRD-v1.md` 落地 MVP。
- 第一阶段仅聚焦招聘端流程，不做谈薪和视频面试。
- 先接入 BOSS 平台，但采用统一连接器抽象，后续可快速扩展智联/猎聘/拉勾等平台。

## 2. 本期范围

### 2.1 In Scope
- 自动发布招聘要求（JD 发布）。
- 自动打招呼（候选人触达）。
- 自动接收简历（渠道拉取/回收）。
- 简历解析与匹配分析（评分与解释）。
- 自动回复（FAQ 与意向确认场景）。
- 自动约面试（时间收集、冲突检测、日历落地）。

### 2.2 Out of Scope
- 谈薪自动化（含薪资博弈 Agent）。
- 实时视频面试与 AI 面试官。
- Offer 自动发放全自动闭环。

## 3. 交付原则
- `API-first`：优先走接口能力，网页自动化仅兜底。
- `Connector 抽象优先`：业务层不直接依赖 BOSS 细节。
- `AI 辅助决策 + 人工审批`：高风险动作必须可拦截。
- `可审计`：所有关键动作有日志与事件追踪。

## 4. 技术方案（抽象优先）

### 4.1 分层架构
- `Channel Connector Layer`：各招聘平台适配器（BOSSConnector、ZhilianConnector...）。
- `Recruitment Core`：职位、候选人、会话、面试排期、状态机。
- `AI Services`：简历解析、评分、回复生成、约面建议。
- `Agent Orchestrator`：任务规划、工具调用、策略执行、重试补偿。
- `Governance`：审批、权限、审计、告警。

### 4.2 Connector 统一接口（MVP）
```python
class RecruitingConnector(Protocol):
    def publish_job(self, job_payload: dict) -> dict: ...
    def sync_job_status(self, external_job_id: str) -> dict: ...
    def list_applicants(self, job_external_id: str, cursor: str | None) -> dict: ...
    def send_greeting(self, candidate_external_id: str, template_id: str, vars: dict) -> dict: ...
    def fetch_messages(self, conversation_external_id: str, cursor: str | None) -> dict: ...
    def send_message(self, conversation_external_id: str, message: str) -> dict: ...
    def schedule_interview(self, candidate_external_id: str, slot: dict) -> dict: ...
```

### 4.3 数据标准化对象
- `UnifiedJob`
- `UnifiedCandidate`
- `UnifiedConversation`
- `UnifiedInterview`
- `UnifiedEvent`（发布成功、触达成功、回复失败、约面完成等）

## 5. 里程碑与排期（4 周）

## Week 1：基础设施与 BOSS 连接器骨架
- 目标：搭建可扩展架构，打通最小闭环骨架。
- 开发项：
- 定义 Connector 接口与 `BOSSConnector` 空实现。
- 建立核心数据模型（Job/Candidate/Conversation/Interview/Event）。
- 建立任务队列、重试机制、幂等键中间件。
- 建立审批与审计日志框架。
- 交付物：
- `connector` 抽象层代码与 BOSS 适配项目结构。
- 核心表结构与迁移脚本。
- 基础 API 骨架（jobs/candidates/conversations/interviews）。
- 验收：
- 可完成本地“创建岗位 -> 调用 BOSSConnector.publish_job（mock）-> 回写状态”。

## Week 2：发布、简历接收、解析分析
- 目标：实现“发布 + 收简历 + 初筛”闭环。
- 开发项：
- 完成 BOSS 发布与状态同步能力（真实或半真实环境）。
- 完成候选人拉取、去重、入库流程。
- 完成简历解析（结构化）与匹配评分（规则+模型）服务。
- 建立候选人状态机：`new -> parsed -> screen_pass/contacted`。
- 交付物：
- 可用接口：发布、状态查询、候选人同步、简历评分。
- 数据看板初版：入库数、解析成功率、通过率。
- 验收：
- “岗位发布 -> 候选人入库 -> 简历评分”链路可跑通，解析成功率达到 PRD 指标。

## Week 3：自动打招呼、自动回复、人工接管
- 目标：实现“触达 + 沟通”自动化。
- 开发项：
- 打招呼策略引擎（时间窗、频控、模板变量）。
- 自动回复引擎（FAQ 分类、意向识别、低置信度转人工）。
- 会话状态维护（待回复、已回复、待人工、结束）。
- 审批闸门接入（批量触达、敏感回复先审批）。
- 交付物：
- 可用接口：自动打招呼、自动回复、会话同步。
- 工单台：人工接管队列。
- 验收：
- 候选人会话可自动推进，自动回复准确率达到 PRD 指标。

## Week 4：自动约面、稳定性、灰度上线
- 目标：完成可上线 MVP。
- 开发项：
- 面试时间收集与推荐（候选人偏好 + 面试官日历）。
- 自动排期、改期、提醒、确认回写。
- 稳定性建设：失败补偿、告警规则、SLA 监控。
- 灰度策略：按岗位/候选人比例逐步放量。
- 交付物：
- 可用接口：约面、改期、提醒。
- 运营看板：漏斗、时效、异常率。
- 上线 Runbook 与回滚预案。
- 验收：
- 关键指标达标且连续灰度运行 5 天无 P1 故障。

## 6. 工作拆分（按泳道）

### 6.1 后端平台
- 连接器框架与 BOSS 适配器。
- Recruitment Core API 与状态机。
- 任务编排、重试、幂等、补偿。
- 审计与审批。

### 6.2 AI 能力
- 简历解析 Pipeline（解析、清洗、实体抽取）。
- 匹配评分服务（规则+模型融合）。
- 自动回复与约面建议。
- 安全策略（敏感词、低置信度降级）。

### 6.3 前端与运营
- 岗位管理页、候选人看板、会话台、约面台。
- 审批台与异常处理台。
- 数据看板（漏斗、响应时长、成功率）。

### 6.4 QA 与运维
- 接口自动化测试。
- 渠道变更回归脚本。
- 灰度与告警联动。

## 7. 关键接口开发优先级
- P0：`create_job`、`publish_job`、`sync_applicants`、`parse_resume`、`score_candidate`。
- P0：`auto_greet`、`auto_reply`、`schedule_interview`。
- P0：`approval_create`、`audit_log_query`、`funnel_metrics`。
- P1：`reschedule_interview`、`batch_campaign`、`advanced_analytics`。

## 8. 运行策略（Agent 自动化）
- 每个自动动作必须经过 `Policy Check`：
- 风险低 + 高置信度：自动执行。
- 风险中：自动草拟 + 人工一键确认。
- 风险高：强制人工处理。
- 每次执行写入 `UnifiedEvent`，用于追溯和指标统计。

## 9. 风险与应对
- 渠道策略变更：连接器版本化 + 契约测试 + 手工兜底。
- 自动回复误判：低置信度转人工，关键问题禁自动发送。
- 限流与封禁风险：频控、指数退避、任务错峰。
- 数据合规风险：PII 脱敏、最小权限、审计全量留存。

## 10. 资源计划（建议配置）
- 产品经理 1 人（全程）。
- 后端工程师 2 人（连接器 + 核心服务）。
- AI 工程师 1 人（解析/评分/回复）。
- 前端工程师 1 人（管理台与看板）。
- QA 1 人（接口 + 回归 + 灰度验收）。

## 11. 周度验收清单

### Week 1 验收
- Connector 抽象层完成并有 BOSS 实现骨架。
- 数据模型与审计框架可用。

### Week 2 验收
- 岗位发布与候选人接收链路可运行。
- 简历解析评分可输出结构化结果与解释。

### Week 3 验收
- 自动打招呼、自动回复上线灰度环境。
- 人工接管机制与审批流有效。

### Week 4 验收
- 自动约面可用，改期/提醒正常。
- 灰度指标达标并具备上线回滚能力。

## 12. 里程碑结果定义（DoD）
- 功能 DoD：接口可调用、日志完整、异常可恢复。
- 质量 DoD：测试通过率 >= 95%，关键路径无阻塞缺陷。
- 业务 DoD：达到 PRD 指标（发布成功率、解析成功率、回复准确率、约面成功率）。

