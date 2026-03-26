# AI-HR 可执行 PRD（MVP）

## 1. 基本信息
- 文档版本：v1.0
- 日期：2026-03-18
- 适用周期：4 周 MVP 开发
- 关联文档：`docs/AI-HR-功能分析列表.md`

## 2. 背景与目标
当前招聘流程存在岗位发布慢、简历处理重、沟通响应慢、约面效率低的问题。目标是建设一个 `API-first` 的 AI-HR MVP，在单渠道试点（优先 BOSS）下实现“发布-筛选-沟通-约面”闭环，并保留人工审核闸门。

## 3. 目标与范围

### 3.1 业务目标（MVP）
- 岗位发布时效从小时级降到分钟级。
- 简历初筛自动化覆盖率达到 70% 以上。
- 候选人首轮响应时延降至 10 分钟内。
- 约面成功率达到 70%。

### 3.2 范围内
- 职位创建与多渠道发布（先支持 BOSS 试点）。
- 简历接收、解析、去重、匹配评分。
- 自动打招呼、自动回复（FAQ/意向确认）。
- 自动约面（候选人时间收集 + 面试官日历冲突检测）。
- 审批与审计（高风险动作人工确认）。

### 3.3 范围外
- 全自动 Offer 发放。
- 无人工参与的最终录用决策。
- 复杂薪酬谈判 Agent。

## 4. 用户角色
- 招聘专员（HR）：发岗位、看候选人、处理异常、审批关键动作。
- 面试官：提供可约时间、查看候选人摘要、提交反馈。
- 招聘负责人：看漏斗和质量指标。
- 系统管理员：管理权限、渠道配置、审计。

## 5. 关键流程（E2E）
1. HR 创建岗位并提交审核。
2. Agent 调用渠道连接器发布岗位并回写状态。
3. 系统接收简历并完成解析、去重、评分。
4. Agent 对入围候选人自动打招呼并维护会话状态。
5. 候选人回复后，Agent 自动答疑并推进约面。
6. Agent 自动计算可约时间并发起会议邀请。
7. 全链路写入审计日志与指标系统。

## 6. 需求清单（可执行）

| 编号 | 需求 | 优先级 | 验收标准 |
|---|---|---|---|
| FR-001 | 职位模板与创建 | P0 | 可保存模板并创建岗位，字段校验通过率 100% |
| FR-002 | 职位发布到渠道 | P0 | 发布成功率 >= 95%，失败可重试 |
| FR-003 | 发布状态回收 | P0 | 10 分钟内同步发布状态 |
| FR-004 | 简历接收入库 | P0 | 新简历 2 分钟内入库 |
| FR-005 | 简历解析 | P0 | 结构化解析成功率 >= 92% |
| FR-006 | 去重合并 | P0 | 重复候选人识别准确率 >= 95% |
| FR-007 | 匹配评分 | P0 | 输出总分和至少 3 个维度解释 |
| FR-008 | 自动打招呼 | P0 | 入围候选人可批量触达，失败可追踪 |
| FR-009 | 自动回复 | P0 | FAQ 场景自动回复准确率 >= 85% |
| FR-010 | 自动约面 | P0 | 约面成功率 >= 70%，冲突可自动改期 |
| FR-011 | 人工审批闸门 | P0 | 批量触达/拒信/Offer 必须审批后执行 |
| FR-012 | 审计日志 | P0 | 关键动作可追溯率 100% |
| FR-013 | 漏斗报表 | P0 | 可查看阶段转化率与时长 |

## 7. 状态机定义

### 7.1 候选人状态
- `new`：新入库
- `parsed`：已解析
- `screen_pass`：初筛通过
- `contacted`：已触达
- `engaged`：已互动
- `interview_scheduled`：已约面
- `interview_done`：面试完成
- `rejected`：淘汰
- `offer_pending`：待发 Offer
- `hired`：录用

### 7.2 状态流转约束
- `new -> parsed -> screen_pass` 由系统自动流转。
- `screen_pass -> contacted` 可由 Agent 自动执行。
- `engaged -> interview_scheduled` 需满足候选人确认或时间锁定。
- `rejected` 与 `offer_pending` 需要审批策略校验。

## 8. 接口清单（MVP）

### 8.1 对外业务接口（BFF/API Gateway）

| 接口ID | 方法 | 路径 | 说明 | 幂等键 |
|---|---|---|---|---|
| API-001 | POST | `/api/v1/jobs` | 创建岗位 | `x-idempotency-key` |
| API-002 | POST | `/api/v1/jobs/{job_id}/publish` | 发布岗位到渠道 | `x-idempotency-key` |
| API-003 | GET | `/api/v1/jobs/{job_id}/publish-status` | 查询发布状态 | 无 |
| API-004 | POST | `/api/v1/candidates/import` | 导入候选人/简历 | `x-idempotency-key` |
| API-005 | POST | `/api/v1/candidates/{id}/score` | 触发匹配评分 | 无 |
| API-006 | POST | `/api/v1/conversations/greet` | 自动打招呼 | `x-idempotency-key` |
| API-007 | POST | `/api/v1/conversations/reply` | 自动回复消息 | 无 |
| API-008 | POST | `/api/v1/interviews/schedule` | 创建面试安排 | `x-idempotency-key` |
| API-009 | POST | `/api/v1/approvals` | 发起审批 | 无 |
| API-010 | GET | `/api/v1/metrics/funnel` | 获取漏斗报表 | 无 |

### 8.2 渠道连接器接口（内部）

| 接口ID | 方法 | 路径 | 说明 |
|---|---|---|---|
| INT-001 | POST | `/internal/connectors/{channel}/publish-job` | 渠道发布岗位 |
| INT-002 | GET | `/internal/connectors/{channel}/applicants` | 拉取候选人列表 |
| INT-003 | POST | `/internal/connectors/{channel}/send-message` | 发送沟通消息 |
| INT-004 | POST | `/internal/connectors/{channel}/schedule-interview` | 渠道侧约面动作 |
| INT-005 | GET | `/internal/connectors/{channel}/events` | 拉取渠道事件增量 |

### 8.3 Agent 工具接口（内部）

| 工具ID | 方法 | 路径 | 说明 |
|---|---|---|---|
| TOOL-001 | POST | `/internal/tools/create_outreach_plan` | 生成触达计划 |
| TOOL-002 | POST | `/internal/tools/generate_reply` | 生成回复草稿 |
| TOOL-003 | POST | `/internal/tools/propose_slots` | 生成可约时间建议 |
| TOOL-004 | POST | `/internal/tools/risk_check` | 高风险动作校验 |

### 8.4 关键接口示例

`POST /api/v1/jobs/{job_id}/publish`
```json
{
  "channels": ["boss"],
  "strategy": {
    "publish_now": true,
    "retry": 3
  }
}
```

返回：
```json
{
  "ok": true,
  "data": {
    "job_id": "job_123",
    "channels": [
      {"channel": "boss", "status": "published", "external_job_id": "bz_9988"}
    ]
  }
}
```

`POST /api/v1/conversations/reply`
```json
{
  "candidate_id": "cand_1001",
  "conversation_id": "conv_9001",
  "channel": "boss",
  "message": "请问岗位是双休吗？",
  "policy": {"auto_send_threshold": 0.85}
}
```

返回：
```json
{
  "ok": true,
  "data": {
    "reply_text": "该岗位为双休，法定节假日正常休息。",
    "confidence": 0.91,
    "sent": true
  }
}
```

## 9. 数据模型（核心字段）

### 9.1 Job
- `job_id`
- `title`
- `department`
- `city`
- `salary_range`
- `requirements`
- `status`

### 9.2 Candidate
- `candidate_id`
- `name`
- `phone_hash`
- `email_hash`
- `resume_url`
- `source_channel`
- `current_stage`

### 9.3 Conversation
- `conversation_id`
- `candidate_id`
- `channel`
- `last_message`
- `last_sender`
- `intent`

### 9.4 Interview
- `interview_id`
- `candidate_id`
- `interviewer_ids`
- `start_time`
- `end_time`
- `meeting_link`
- `status`

## 10. 非功能要求
- 可用性：核心接口月可用性 >= 99.5%。
- 性能：95 分位接口响应 <= 800ms（不含第三方渠道时延）。
- 安全：PII 存储脱敏，传输全程 TLS。
- 合规：关键动作保留审计日志 >= 180 天。
- 稳定性：支持重试、幂等、失败补偿任务。

## 11. BOSS 接入实施说明（基于当前仓库）
- 当前代码库已有 `search/greet/chat/interviews` 能力，可用于候选人触达与会话读取试点。
- 招聘端“发布职位、收简历、约面执行”需新增招聘者侧连接器能力。
- 技术策略：先接入可用 API；不可用能力以人工任务或网页兜底执行，不直接阻塞主流程。

## 12. 4 周开发排期（可执行）

### Week 1：基础能力与数据底座
- 目标：打通岗位、候选人、流程的核心数据链路。
- 交付：
- API-001/API-004 基础可用。
- 候选人状态机落库与流转规则。
- 审计日志框架（操作人、动作、时间、结果）。
- BOSS 连接器骨架（认证、限流、错误码映射）。
- 验收：
- 可完成“创建岗位 -> 导入候选人 -> 入库可见”。

### Week 2：发布与初筛自动化
- 目标：完成发布与筛选闭环。
- 交付：
- API-002/API-003，INT-001/INT-005。
- 简历解析、去重、评分（FR-005/006/007）。
- 漏斗基础看板 API-010（阶段数量、转化率）。
- 验收：
- 可完成“创建岗位 -> 发布渠道 -> 拉回候选人 -> 打分入围”。

### Week 3：沟通与约面自动化
- 目标：完成沟通和排期闭环。
- 交付：
- API-006/API-007/API-008。
- TOOL-001/002/003/004 与审批 API-009。
- 日历对接（至少一个企业日历源）与会议链接生成。
- 验收：
- 可完成“自动打招呼 -> 自动回复 -> 自动约面 -> 写回状态”。

### Week 4：稳定性、灰度与上线
- 目标：可灰度上线并可运维。
- 交付：
- 失败补偿、重试队列、告警规则。
- 审计报表与关键 SLA 看板。
- 灰度策略（10% 岗位/候选人）和回滚预案。
- UAT 与上线手册。
- 验收：
- 连续 5 天灰度运行，关键指标达标且无 P1 故障。

## 13. 资源与分工建议
- 产品经理：需求澄清、验收口径、灰度策略。
- 后端工程师：API、连接器、任务编排、审计。
- 算法/AI 工程师：解析、评分、回复策略、安全策略。
- 前端工程师：岗位与候选人看板、审批台、报表页。
- QA：回归测试、稳定性验证、UAT 协调。

## 14. 风险与应对
- 渠道规则变化风险：连接器适配层版本化，保留人工接管。
- 自动回复误判风险：低置信度转人工，敏感意图禁自动发送。
- 调度冲突风险：约面前二次校验日历，失败自动改期。
- 合规风险：默认最小权限、全量审计、敏感字段脱敏。

## 15. 上线验收标准（Go/No-Go）
- 发布成功率 >= 95%。
- 简历解析成功率 >= 92%。
- 自动回复准确率 >= 85%（人工抽检）。
- 约面成功率 >= 70%。
- 审计覆盖率 100%，无高危安全漏洞。

