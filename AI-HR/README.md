# AI-HR

AI-HR backend service extracted from the initial BOSS automation exploration.

## Stack
- FastAPI
- SQLAlchemy 2.x
- MySQL
- Vue 3 frontend planned separately

## Current Scope
- Job management API
- Conversation automation API (greet/sync/reply)
- Connector abstraction layer
- BOSS connector skeleton
- Unified response envelope and exception handling

## 中文功能清单
- 已实现功能（仅基于代码落地）：[`docs/AI-HR-已实现功能清单.md`](./docs/AI-HR-已实现功能清单.md)

## Environment
- Default development config file: `.env.dev`
- Default production config file: `.env.prod`
- Example config template: `.env.example`
- You can switch environment by setting `AI_HR_ENV=dev` or `AI_HR_ENV=prod`
- You can also explicitly choose a file with `AI_HR_ENV_FILE=/absolute/path/to/.env.custom`

## Run
```bash
pip install -e .[dev]
AI_HR_ENV=dev ai-hr-api
```

## Provider Health

- Basic health: `GET /health`
- Provider health and circuit snapshot: `GET /health/providers`

## RTC/ASR/TTS Runtime Config

- `AI_HR_RTC_PROVIDER=mock|livekit`
- `AI_HR_LIVEKIT_BASE_URL`
- `AI_HR_LIVEKIT_API_KEY`
- `AI_HR_LIVEKIT_API_SECRET`
- `AI_HR_ASR_PROVIDER=mock|<provider>`
- `AI_HR_TTS_PROVIDER=mock|<provider>`
- `AI_HR_AI_INTERVIEW_RTC_ASR_INGEST_WS_ENABLED=true|false`

## RTC Room ASR Ingest (WebSocket)

- Ingest endpoint:
  - `ws(s)://<host>/api/v1/ai/interviews/rtc/asr/ingest/ws`
- Accepted payload:
  - `{"type":"audio_frame","payload":{"room_id","seq","frame_id","audio_base64","chunk_index","chunk_total","is_final",...}}`
- Server events:
  - `ingest.connected`
  - `ingest.ack` (`accepted|duplicate`)
  - `ingest.result`
  - `ingest.error`
- Smoke script example:
```bash
uv run --project AI-HR python AI-HR/scripts/rtc_asr_ingest_ws_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --api-prefix /api/v1 \
  --room-id <rtc_room_id> \
  --wav-file ./sample.wav \
  --simulate-webhook
```

## AI Interview Redis Runtime

- `AI_HR_REDIS_URL=redis://127.0.0.1:6379/0`
- `AI_HR_AI_INTERVIEW_REDIS_ENABLED=true|false`
- `AI_HR_AI_INTERVIEW_REDIS_PREFIX=aihr`
- `AI_HR_AI_INTERVIEW_QUESTION_PACK_TTL_SECONDS` (default `172800`)
- `AI_HR_AI_INTERVIEW_STATE_TTL_SECONDS` (default `172800`)
- `AI_HR_AI_INTERVIEW_DEDUP_TTL_SECONDS` (default `86400`)
- `AI_HR_AI_INTERVIEW_FOLLOWUP_CACHE_TTL_SECONDS` (default `180`)
- `AI_HR_AI_INTERVIEW_PREBUILD_PACK_TTL_SECONDS` (default `604800`)
- `AI_HR_AI_INTERVIEW_REDIS_EVENT_BUS_ENABLED=true|false`

## Production Run
```bash
AI_HR_ENV=prod ai-hr-api
```

## AI Interview DB Migration (DB-002A)

- Forward migration:
  - `sql/migrations/20260321_ai_interview_online_indexes.sql`
- Rollback migration:
  - `sql/migrations/20260321_ai_interview_online_indexes_rollback.sql`

Example:
```bash
mysql -u <user> -p <db_name> < AI-HR/sql/migrations/20260321_ai_interview_online_indexes.sql
```

Rollback example:
```bash
mysql -u <user> -p <db_name> < AI-HR/sql/migrations/20260321_ai_interview_online_indexes_rollback.sql
```

## AI Interview Lifecycle Cleanup (DB-003A)

- Dry-run:
```bash
uv run --project AI-HR python AI-HR/scripts/ai_interview_lifecycle_cleanup.py --dry-run --batch-size 500
```
- Execute:
```bash
uv run --project AI-HR python AI-HR/scripts/ai_interview_lifecycle_cleanup.py --batch-size 500
```
- Cleanup audit event:
  - `event_type=ai_interview.lifecycle.cleanup`
  - payload includes `dry_run/batch_size/*_candidates/*_cleared/event_deleted`.

## Technical Question Quality Baseline

- Baseline metrics for interview quality:
  - coverage (`coverage_rate`, `dimension_coverage_rate`, `keyword_coverage_rate`)
  - duplication (`duplication_rate`)
  - follow-up depth (`followup_depth`)
  - response latency (`avg_response_latency_ms`, `response_latency_p95_ms`)
- Example:
```bash
uv run --project AI-HR python AI-HR/scripts/tech_question_quality_baseline.py --window-hours 72 --limit 200 --output AI-HR/tmp/tech_question_quality_baseline.json
```
- Evaluate specified sessions:
```bash
uv run --project AI-HR python AI-HR/scripts/tech_question_quality_baseline.py --session-id <session_id_1> --session-id <session_id_2>
```

## BOSS Live Integration
- Switch to live mode: `AI_HR_BOSS_MODE=live`
- Configure endpoints:
  - `AI_HR_BOSS_BASE_URL`
  - `AI_HR_BOSS_PUBLISH_PATH`
  - `AI_HR_BOSS_STATUS_PATH`
  - `AI_HR_BOSS_APPLICANTS_PATH`
  - `AI_HR_BOSS_GREET_PATH`
  - `AI_HR_BOSS_FETCH_MESSAGES_PATH`
  - `AI_HR_BOSS_SEND_MESSAGE_PATH`
- Auth options (either one):
  - `AI_HR_BOSS_COOKIE_HEADER` (raw Cookie header)
  - `AI_HR_BOSS_CREDENTIAL_FILE` (defaults to `~/.config/boss-cli/credential.json`)
- Optional token header: `AI_HR_BOSS_SECRET` will be sent as `Authorization: Bearer <secret>`

## Structure
- `ai_hr/`: backend service code
- `tests/`: backend tests
- `docs/`: PRD, plan, and Jira breakdown
