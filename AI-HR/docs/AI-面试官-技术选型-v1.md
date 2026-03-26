# AI 面试官技术选型 v1（2026-03-21）

## 1. 目标

- 支持生产级实时音视频面试与弱网重连。
- 支持 LLM 题目生成与实时追问。
- 保证低时延、可观测、可回滚、可灰度。

## 2. 主链路选型

### 2.1 RTC（音视频）

- 主选：LiveKit
- 选型理由：
  - 房间、权限、重连能力成熟；
  - 支持服务端 webhook 事件回写；
  - 支持云与自建部署形态。

### 2.2 LLM（题目生成/追问）

- 主选：OpenAI（Responses/Reatime 双链路）
- 选型理由：
  - 文本结构化输出能力稳定，适合问题树生成；
  - Realtime 模式适合语音面试实时追问场景；
  - 支持运行时策略路由与灰度。

### 2.3 ASR/TTS

- 主选：由 LLM/Realtime 一体化链路承载；
- 备选：独立 ASR/TTS Provider（用于故障降级与成本优化）。

## 3. 失败降级与回滚

- LLM 超时/失败：降级到 `rule_only`；
- ASR 失败：降级为文本输入；
- TTS 失败：降级为文本播报；
- RTC 供应商故障：停止新建会话，存量会话保留文本链路。

## 4. 观测与 SLA

- 关键指标：
  - `asr_latency_p95_ms`
  - `llm_latency_p95_ms`
  - `tts_latency_p95_ms`
  - `e2e_latency_p95_ms`
  - `handoff_rate`
  - `blocked_rate`
- 基线目标：
  - E2E 语音轮次 P95 <= 1800ms
  - ASR P95 <= 700ms

## 5. 成本治理

- 策略：`cost_first / balanced / quality_first`
- 路由字段：`model_route_policy`
- 审计字段：记录模型与提示词版本，支持结算核对。

## 6. 合规与安全

- 连接密钥仅通过环境变量或密钥管理服务注入；
- 音频/转写生命周期策略必须配置；
- 全链路事件可审计，支持 operator/session/job 维度检索。
