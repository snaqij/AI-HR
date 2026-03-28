# AI-HR Architecture Specification (v1)

## 1. Purpose and Scope
This document defines the architecture of the AI-HR system for realtime AI interview and hiring workflow automation. It clarifies module boundaries, core data flows, reliability strategy, and evolution direction.

In scope:
- AI interview session lifecycle
- Realtime speech pipeline (ASR -> LLM -> TTS -> playback)
- Runtime policy, observability, and governance
- Data persistence and cache strategy
- External integrations (LiveKit, speech providers, LLM providers)

Out of scope:
- Frontend UI/visual design details
- Vendor-internal implementation details
- Organization-level BI/reporting platform

## 2. Product Goals and Architecture Principles
### 2.1 Product Goals
- Low-latency realtime interview interaction
- Stable and controllable AI behavior in production
- High observability for debugging and continuous optimization
- Provider-agnostic architecture with pluggable capabilities

### 2.2 Architecture Principles
- Layered design, explicit boundaries
- Event-driven realtime orchestration
- Provider abstraction + runtime configuration
- Safety first: guardrails, deduplication, fallback, circuit protection
- Measure first: traceability for every critical latency segment

## 3. System Context
AI-HR consists of:
- Frontend client (Vue): audio capture, realtime socket, transcript/TTS playback
- Backend API (FastAPI): orchestration, policy, persistence, integration
- Persistent storage (MySQL): sessions, turns, reports, observability
- Runtime store (Memory/Redis): question pack, flow state, dedup and cache
- External providers:
  - ASR (currently Aliyun NLS in dev config)
  - LLM (OpenAI-compatible HTTP streaming)
  - TTS (Tencent, PCM-oriented streaming path)
  - RTC (LiveKit gateway)

## 4. Logical Architecture
### 4.1 Layered View
1. Interface Layer  
FastAPI routes provide REST + WebSocket endpoints for session control and realtime duplex traffic.

2. Application Service Layer  
`AIInterviewService` coordinates interview lifecycle, realtime chunk processing, event append, follow-up generation, and TTS dispatch.

3. Domain/Policy Layer  
Interview stage machine, question flow engine, decision policy, and LLM guardrails define behavior and risk control.

4. Orchestration Layer  
Realtime orchestrator executes ASR/policy/LLM/TTS pipeline and emits incremental events.

5. Provider Adapter Layer  
Speech/LLM/RTC providers are encapsulated behind stable interfaces (`ASRProvider`, `TTSProvider`, LLM client/router, RTC gateway).

6. Repository Layer  
Repositories isolate database operations and provide durable event/session/report storage.

7. Runtime State Layer  
Memory/Redis runtime store caches short-lived state: question packs, followup cache, dedup windows, prebuilt packs.

### 4.2 Key Modules
- `ai_hr/api/routes/ai_interviews.py`: API and duplex WS entry points
- `ai_hr/services/ai_interviews.py`: interview core service and realtime handling
- `ai_hr/services/orchestrator/realtime.py`: pipeline orchestration
- `ai_hr/services/llm/*`: route, prompt, guardrail, invocation
- `ai_hr/services/speech/*`: ASR/TTS provider implementations
- `ai_hr/services/interview_runtime/*`: runtime cache/state abstraction
- `ai_hr/repositories/*`: persistence access layer

## 5. Core Realtime Flow
### 5.1 End-to-End Path
1. Frontend captures microphone PCM frames (AudioWorklet-based capture path).
2. Frames are sent to backend duplex WS as ordered `audio_chunk` messages.
3. Backend sequentially consumes chunks to preserve turn order.
4. ASR produces partial/final transcript updates.
5. On final candidate turn, backend appends event and triggers LLM follow-up generation.
6. LLM output is streamed sentence-by-sentence into TTS.
7. TTS audio packets are pushed to frontend over duplex WS (binary path).
8. Frontend plays PCM packets and updates realtime transcript state.

### 5.2 Turn Finalization Strategy
- Frontend endpointing uses speech/silence windowing and confirmation timing to avoid premature final.
- Backend uses pending flush timing to reduce sentence-tail loss and cross-turn contamination.
- Deduplication exists at frame/event levels to avoid repeated processing.

## 6. Data and State Design
### 6.1 Durable Data (MySQL)
Core entities include:
- Interview session
- Interview turn/event
- Question set
- Interview report
- AI request traces and decision logs

Design intent:
- Session-centric timeline reconstruction
- Auditable AI behavior
- Post-hoc quality and latency analytics

### 6.2 Ephemeral Runtime State (Memory/Redis)
- Question pack and version snapshot
- Question-flow state
- Followup cache and prebuild cache
- Realtime dedup windows and short-lived pending states

Benefits:
- Lower DB pressure
- Faster orchestration decisions
- Better horizontal scalability with Redis mode

## 7. Reliability and Performance Design
### 7.1 Reliability Mechanisms
- Provider health checks and circuit breaker
- Retry and fallback policies per provider category
- WS frame dedup and queue-based ordered consumption
- Graceful degradation when LLM/TTS is unavailable

### 7.2 Latency Design
Critical latency segments:
- Endpoint detection latency
- ASR final stabilization latency
- LLM first-token latency
- TTS first-packet latency
- Transport and playback startup latency

Current optimization focus:
- Single binary playback path
- PCM codec consistency checks
- Reduced redundant realtime branches
- Queue/timeout tuning for realtime stability

## 8. Safety, Compliance, and Governance
- Input/output guardrails for AI generation
- Policy flags on sensitive or risky turns
- Event-level observability for audit and replay
- Feature flags for controlled rollout of AI capabilities
- Retention and cleanup jobs for lifecycle governance

## 9. Observability and Operations
### 9.1 Telemetry
- Per-turn latency breakdown (`asr_ms`, `llm_ms`, `tts_ms`, `e2e_ms`)
- Followup repeat rate and completion metrics
- Duplex ack/loss/queue indicators
- Provider-level error and timeout diagnostics

### 9.2 Operational Workflow
- Use health endpoints for baseline status
- Use session replay + trace logs for incident root cause
- Use runtime flags to isolate risky features quickly
- Use benchmark scripts for regression and capacity tests

## 10. Deployment and Configuration
- Environment-driven config (`.env.dev`, `.env.prod`)
- Provider selection is runtime-configurable
- Support for local memory mode and Redis-enhanced mode
- LiveKit integration controlled by explicit feature flags

Recommended production posture:
- Explicit provider keys and timeouts
- Redis enabled for runtime state and event distribution
- Strict observability retention and cleanup policy

## 11. Known Risks and Evolution Plan
### 11.1 Current Risks
- Realtime branch complexity can introduce duplicate work under misconfiguration
- Provider protocol mismatch may surface as codec/timeout issues
- Long-tail latency spikes from downstream model or network instability

### 11.2 Evolution Roadmap
1. Unify realtime generation path and remove duplicated branches
2. Strengthen true streaming protocol handling and backpressure control
3. Build standardized latency SLO dashboards (p50/p95/p99 by segment)
4. Add chaos and failover drills for provider outages
5. Introduce multi-provider routing by quality/latency policy

## 12. Summary
AI-HR is a modular, provider-agnostic, event-driven architecture designed for realtime AI interview interactions. Its strength lies in explicit layering, runtime configurability, and observability-first operation. The next stage should focus on path unification, streaming protocol hardening, and SLO-driven optimization to deliver both low latency and production-grade stability.

