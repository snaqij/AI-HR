# AI-HR 技术架构说明书（代码深度对齐版 v1.1）

## 1. 文档说明

### 1.1 文档目标
本文档用于完整说明 AI-HR 当前版本的技术架构，强调“基于现有代码实现”的事实，而非抽象方案。文档面向研发、测试、运维、技术评审场景，核心目标是回答四个问题：

1. 系统是如何工作的（端到端链路与模块协作）。  
2. 系统为什么这样设计（时延、稳定性、可扩展性权衡）。  
3. 当前有哪些真实瓶颈与风险（而非理论风险）。  
4. 下一步如何按优先级演进（可执行的工程路线）。

### 1.2 范围边界
本文档覆盖：
- 前端语音采集与双工通信
- 后端实时处理（ASR、LLM、TTS 编排）
- 数据持久化与运行时状态
- 可观测性、容错与性能治理

本文档不覆盖：
- 业务流程 PRD 细节
- UI/交互视觉设计细节
- 供应商内部黑盒实现

---

## 2. 系统总体架构（当前实现）

AI-HR 是一个“实时语音面试系统”，架构风格为：**分层解耦 + 事件驱动 + Provider 抽象**。  
在当前代码中，系统由以下部分构成：

1. 前端（Vue）
- 通过 `AudioWorklet` 采集单声道音频。
- 以 150ms 窗口做端点检测（语音/静音）。
- 通过双工 WS 发送 `audio_chunk`。
- 接收后端 `duplex.tts.packet + binary PCM` 并即时播放。

2. 后端 API（FastAPI）
- 提供会话生命周期接口与实时 WS 接口。
- 在双工接口中负责：ack、队列、线程任务、事件分发、错误回传。

3. 应用服务层（AIInterviewService）
- 负责“分片处理 -> 回合提交 -> 事件入库 -> 追问生成”的主业务流程。
- 管理 pending flush、预取、去重等实时状态。

4. 编排层（RealtimeOrchestrator）
- 负责 ASR/策略/LLM/TTS 的串联逻辑与延时分段统计。

5. Provider 层
- ASR：当前 dev 配置为 `aliyun_nls`。
- LLM：当前 dev 配置为 OpenAI 兼容 HTTP 流式。
- TTS：当前 dev 配置为 Tencent，PCM，WS 主路径。

6. 存储层
- MySQL：会话、轮次、题集、报告、可观测日志。
- 运行时存储（Memory/Redis）：题包、状态机、去重窗口、followup 缓存。

---

## 3. 代码结构与职责映射

### 3.1 路由层
关键文件：`ai_hr/api/routes/ai_interviews.py`

关键接口：
- `/ai/interviews/rtc/asr/ingest/ws`
- `/ai/interviews/sessions/{session_id}/events/ws`
- `/ai/interviews/sessions/{session_id}/rtc/duplex/ws`

路由层职责不是做业务决策，而是：
1. 鉴权与协议适配。  
2. 快速确认（ack）和背压反馈。  
3. 将请求转交服务层并封装回包。  
4. 管理实时任务生命周期（task/thread/queue）。

### 3.2 服务层
关键文件：`ai_hr/services/ai_interviews.py`

核心函数：
- `process_duplex_audio_chunk`: 双工分片处理入口。  
- `append_event`: final 文本入库与 followup 触发。  
- `_schedule_pending_asr_flush`: 延迟 flush 防止尾字丢失。  
- `_maybe_prefetch_partial_followup`: partial 触发预取/试探流程。  

服务层是系统“业务真相中心”，负责维护回合边界、状态一致性和事件可追溯。

### 3.3 编排层
关键文件：`ai_hr/services/orchestrator/realtime.py`

核心函数：`process_candidate_turn`  
执行顺序：
1. 获取转写文本（直接 transcript 或 ASR）。
2. 计算 action/reason/policy_flags。
3. 触发 LLM followup（支持流式）。
4. 触发 TTS（支持流式迭代包）。
5. 返回延时分段 `asr_ms/llm_ms/tts_ms/e2e_ms`。

### 3.4 Provider 层
关键文件：
- `ai_hr/services/speech/aliyun_providers.py`
- `ai_hr/services/speech/tencent_providers.py`
- `ai_hr/services/llm/client.py`
- `ai_hr/services/speech/factory.py`

Provider 层目标是“隔离供应商差异”，对上层暴露统一抽象能力。

---

## 4. 端到端主链路（实时面试）

本节以当前代码的真实执行路径描述。

### 4.1 前端采集与句尾判定
文件：`frontend/src/App.vue`

关键参数：
- `ANALYZE_INTERVAL_MS = 150`
- `PAUSE_WINDOWS_TO_COMMIT = 2`
- `CANDIDATE_END_SILENCE_WINDOWS = 3`
- `COMMIT_CONFIRM_MS = 350`
- `MIN_FINAL_GAP_MS = 700`
- `MIN_SENTENCE_MS_FOR_FINAL = 1200`

这意味着：final 触发并非“静音即提交”，而是有“候选句尾 + confirm”双阶段。

### 4.2 前端发送策略
函数：`sendDuplexChunk`、`submitSentenceAudio`

当前 duplex 模式策略：
1. 语音中持续发送非 final 分片。  
2. final 时不再重发整句历史音频，而是发送极短 marker（`DUPLEX_FINAL_MARKER_SAMPLES=160`）+ `is_final=true`。  
3. 通过 `frame_id` 追踪 ack，并做超时重传控制。

设计意图是避免“历史音频二次发送导致重复识别”。

### 4.3 后端接收与顺序处理
文件：`ai_hr/api/routes/ai_interviews.py`

双工路由内部队列：
- `audio_chunk_queue(maxsize=128)`：音频处理主队列
- `sentence_queue(maxsize=128)`：LLM 句子队列
- `packet_queue(maxsize=256)`：TTS 音频包队列

处理流程：
1. 路由收到分片后先返回 `duplex.ack`。  
2. 分片入 `audio_chunk_queue`，由 `_audio_queue_consumer` 串行消费。  
3. 串行消费确保分片顺序，避免竞态导致 ASR 状态污染。

### 4.4 服务层分片处理
函数：`process_duplex_audio_chunk`

非 final：
- 走 ASR partial 路径，发布 `asr.turn`，并可能触发 partial 预取。

final：
- 调用 `asr_stream` 收敛文本。
- 安排 `_schedule_pending_asr_flush(delay=0.9)`。
- 构造 `AIInterviewSessionEventRequest` 并调用 `append_event`。

### 4.5 append_event 与 followup
函数：`append_event`

当前代码中，对 candidate final 回合会强制走 LLM followup 路径：
- `llm_enabled=True`
- `decide_action=lambda ...: ("auto_continue", "force_llm_after_final", [])`

随后：
1. 落库 `turn`。  
2. 发布 `session.event`。  
3. 通过事件总线向前端链路传播 followup 与音频包信息。

### 4.6 LLM 调用与流式输出
文件：`ai_hr/services/llm/client.py`

当前实现为 OpenAI 兼容 HTTP 流式（SSE）读取：
- `urllib.request.urlopen(..., timeout=route.timeout_seconds)`
- 读取 `data:` 行并抽取 delta 文本

当前 dev 参数：
- `AI_HR_LLM_TIMEOUT_SECONDS=20`
- `AI_HR_LLM_MAX_RETRIES=2`

这套参数偏“稳态容错”，对实时首包不算激进。

### 4.7 TTS 生成与二进制回推
文件：`ai_hr/services/speech/tencent_providers.py`

当前目标路径：
- 强制 codec 为 `pcm`
- 使用 WS 流式主路径（`_synthesize_stream_iter_ws`）
- 生成 `audio_bytes + audio_codec + sample_rate`

路由分发时做硬校验：
- `audio_bytes` 必须存在
- `audio_codec` 必须是 `pcm`
- 元信息固定 `transport=binary` 后发送二进制 PCM

前端以 `playRawPcm` 播放。

---

## 5. 数据架构与状态管理

### 5.1 持久化数据（MySQL）
核心实体：
1. `ai_interview_session`：会话主记录。  
2. `ai_interview_turn`：候选人与系统轮次事件。  
3. `ai_interview_question_set`：题集版本快照。  
4. `ai_interview_report`：面试评估与建议。  
5. `ai_request_trace`、`ai_decision_log`：可观测与审计数据。

设计目的：
- 可回放（replay）
- 可审计（decision trace）
- 可评估（quality/latency metrics）

### 5.2 运行时状态（Memory/Redis）
存储内容：
1. question pack 与 flow state。  
2. followup cache（减少重复生成）。  
3. dedup 信息（frame/event）。  
4. pending flush timers、prefetch 中间态。  

作用：
- 降低数据库热写压力
- 提高实时链路决策速度
- 支撑多实例扩展（Redis 模式）

---

## 6. 稳定性机制与容错策略

### 6.1 去重与顺序保证
1. 路由层 `frame_id` 去重，重复帧直接 `duplicate` ack。  
2. 服务层 `event_id` 去重，避免重复入库。  
3. 音频分片严格串行消费，避免并发污染 ASR 上下文。

### 6.2 回合边界控制
1. 前端双阶段 endpointing，降低误 final。  
2. 后端 pending flush（0.9s）降低句尾丢失。  
3. ASR provider 侧 epoch 机制控制跨回合串音。

### 6.3 超时与降级
1. LLM 超时/重试由 route 配置控制。  
2. TTS WS 支持可配置 fallback（当前关闭）。  
3. 出错时通过 `duplex.error` 回传，系统不中断。

---

## 7. 可观测体系（现状与缺口）

### 7.1 现有能力
双工路由已维护以下时延样本：
- `ack_latencies_ms`
- `asr_latencies_ms`
- `llm_latencies_ms`
- `tts_latencies_ms`
- `e2e_latencies_ms`

并能输出 `duplex.stats`（含 p50/p95/p99）。

### 7.2 事件观测
事件总线关键事件：
- `asr.turn`
- `llm.sentence`
- `tts.packet`
- `session.event`

这些事件已足以复盘“识别 -> 生成 -> 播放”的时序问题。

### 7.3 主要缺口
1. 缺少统一 `trace_id` 跨前后端贯通。  
2. 首可听时延尚未标准化采集到单一指标。  
3. provider 错误码映射与聚合不统一，告警噪声偏高。

---

## 8. 性能分析（基于当前代码）

### 8.1 主要时延来源
1. 前端 final 判定窗口（静音 + confirm）。  
2. ASR final 收敛等待（Aliyun 路径 `completed_event.wait(timeout=1.2)`）。  
3. LLM 下游超时与重试策略偏保守。  
4. 分支重复工作导致额外开销（见下一节）。

### 8.2 当前结构性风险：重复 TTS 生成
当前实现存在两条路径可能生成 TTS：
1. 编排器在 `process_candidate_turn` 中直接调用 TTS 并 `on_audio_packet` 推送。  
2. duplex 路由监听 `llm.sentence` 后，producer 线程再次调用 `tts_stream_iter`。

影响：
- 同句重复合成
- 成本与时延抬升
- 重复播报概率上升

这是当前架构最需要先治理的技术点之一。

### 8.3 建议性能基线（SLO）
1. 首可听时延 p50 <= 900ms，p95 <= 1500ms。  
2. LLM 首 token p95 <= 700ms。  
3. TTS 首包 p95 <= 500ms。  
4. 包间隔抖动 p95 <= 120ms。

---

## 9. 已知问题与根因归类（工程视角）

### 9.1 ASR 重复/串音类
可能根因：
1. 历史音频二次提交（已通过 final marker 策略缓解）。  
2. flush 时机过早导致 epoch 切换，尾句丢失或错位。  
3. 并发路径未收敛导致回合状态竞争。

### 9.2 LLM 触发异常类
可能根因：
1. final 触发时机偏早，导致文本不完整。  
2. 下游 HTTP 流式读超时，触发重试与回退。  
3. partial 预取与 final 路径并行导致行为难预测。

### 9.3 TTS 异常类
可能根因：
1. 协议事件处理与超时参数不匹配（WS recv timeout）。  
2. 编解码不一致（已强制 PCM + 校验）。  
3. 误判规则过严造成误杀（已收紧 MP3 判定逻辑）。

---

## 10. 配置治理与发布策略

### 10.1 关键配置分组
1. Provider 选择：
- `AI_HR_ASR_PROVIDER`
- `AI_HR_TTS_PROVIDER`
- `AI_HR_LLM_PROVIDER`

2. LLM 实时参数：
- `AI_HR_LLM_TIMEOUT_SECONDS`
- `AI_HR_LLM_MAX_RETRIES`

3. TTS 实时参数：
- `AI_HR_TTS_TENCENT_CODEC`
- `AI_HR_TTS_TENCENT_WS_STREAMING_ENABLED`
- `AI_HR_TTS_TENCENT_WS_ALLOW_HTTP_FALLBACK`
- `AI_HR_TTS_TENCENT_WS_OPEN_TIMEOUT_MS`
- `AI_HR_TTS_TENCENT_WS_RECV_TIMEOUT_MS`

### 10.2 发布建议
1. 所有时延参数变更必须灰度。  
2. 每次发布后跑固定 benchmark 场景并对比 p95。  
3. 任何“路径级”变更（如 TTS 主链路）必须配套回滚开关。

---

## 11. 技术演进路线（可执行）

### P0：链路收敛（立刻执行）
1. 收敛 TTS 到单一路径，彻底消除重复合成。  
2. 固化跨端时序埋点，形成首可听延时真值链。  
3. 将 final 触发策略参数化并统一管理。

### P1：稳定性强化（短期）
1. 分离 LLM connect/read timeout，降低长尾阻塞。  
2. 强化 TTS WS 状态机和错误码映射。  
3. debug 日志改为 session 级采样开关，降低热路径 I/O。

### P2：能力升级（中期）
1. 按“质量/成本/时延”做多模型动态路由。  
2. 建立回归压测门禁（不过阈值不发版）。  
3. 建立统一 SLO 看板与告警系统。

---

## 12. 总结
AI-HR 当前代码已经形成可运行的实时面试系统：前端端点检测、后端双工处理、ASR/LLM/TTS 编排、持久化与观测体系均已具备。  
现阶段关键任务不是“补功能”，而是“收敛路径、稳住协议、压实指标”。  
只要沿着 P0 -> P1 -> P2 执行，系统可以从“可用”升级为“低时延、可预测、可持续演进”的生产级实时 AI 架构。

