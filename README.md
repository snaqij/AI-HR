# AI-HR

> AI Interview and Hiring Automation Platform  
> Build structured interviews, evidence-based evaluation, and production-ready recruitment workflows.

[![CI](https://img.shields.io/github/actions/workflow/status/<org>/<repo>/ci.yml?branch=main)](https://github.com/<org>/<repo>/actions)
[![License](https://img.shields.io/github/license/<org>/<repo>)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/<org>/<repo>?style=social)](https://github.com/<org>/<repo>/stargazers)
[![Issues](https://img.shields.io/github/issues/<org>/<repo>)](https://github.com/<org>/<repo>/issues)

## Why This Project

Most interview tools either:
- generate generic AI questions with weak evidence traceability, or
- provide ATS automation without reliable interview intelligence.

AI-HR bridges both:
- structured interview runtime with turn-level evidence,
- composite assessment (resume + interview + market context),
- decision workflows for advance / review / reject.

## Demo

- Product demo video: `<ADD_YOUTUBE_OR_BILIBILI_LINK>`
- Live preview: `<ADD_PUBLIC_DEMO_LINK>`
- Architecture diagram: `<ADD_ARCH_IMAGE>`

```text
Candidate Answer -> Turn Ingestion -> Interview Runtime -> Assessment -> Decision Policy -> Pipeline Next Step
```

## Core Features

- Interview session lifecycle (create/start/finish/replay/report)
- Question generation (rule + LLM hybrid)
- Realtime ASR/TTS interview loop
- Follow-up orchestration and stage transition control
- Interview evidence binding (question -> answer)
- Assessment and decision policy integration
- Recruiter workflow hooks (review queue, override, publish next step)

## 3-Minute Quickstart

### Prerequisites

- Python `>=3.10`
- Node.js `>=18`
- MySQL and Redis (or your local dev equivalents)

### 1) Start Backend

```bash
cd AI-HR
pip install -e .[dev]
AI_HR_ENV=dev ai-hr-api
```

Backend default: `http://127.0.0.1:8000`

### 2) Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend default: `http://localhost:5173`

### 3) Run an Interview Flow

- Open frontend directly for local demo bootstrap.
- Or pass session params:
  - `/?session_id=<session_id>`
  - `/?candidate_id=<candidate_id>&job_id=<job_id>`

## API Surface (High Level)

- `POST /api/v1/ai/interviews/sessions`
- `POST /api/v1/ai/interviews/sessions/{id}/start`
- `POST /api/v1/ai/interviews/sessions/{id}/events`
- `GET /api/v1/ai/interviews/sessions/{id}/replay`
- `GET /api/v1/ai/interviews/sessions/{id}/report`
- `POST /api/v1/ai/interviews/sessions/{id}/finish`

See full backend docs in [AI-HR/README.md](./AI-HR/README.md).

## Repository Layout

```text
.
├─ AI-HR/        # FastAPI backend, runtime, domain services, SQL migrations, tests
├─ frontend/     # Vue 3 candidate interview room UI
└─ README.md     # You are here
```

## Production Readiness Checklist

- [ ] CI pipeline (lint + tests + build) enabled
- [ ] Secret scanning enabled
- [ ] Security policy published
- [ ] Performance benchmark published
- [ ] Public roadmap maintained
- [ ] Reproducible one-command deployment guide

## Benchmark (Template)

| Metric | Value | Notes |
|---|---:|---|
| Interview turn p95 latency | `<TBD>` | end-of-speech to first response |
| Follow-up repetition rate | `<TBD>` | lower is better |
| Coverage rate | `<TBD>` | required signals covered |
| Decision consistency | `<TBD>` | policy re-run stability |

## Roadmap

- [ ] v0.2: Stable open-source quickstart + CI + docs cleanup
- [ ] v0.3: Multi-policy decision engine + audit dashboard
- [ ] v0.4: Enterprise integration pack (SSO, RBAC, webhooks)
- [ ] v0.5: Multi-language interview quality benchmark suite

## Contributing

Contributions are welcome.

1. Fork this repo
2. Create a feature branch (`feat/<topic>`)
3. Add tests for behavior changes
4. Open a PR with:
   - problem statement
   - change summary
   - test evidence

For major changes, open an issue first to align on design.

## Security

- Do not commit secrets, credentials, or production tokens.
- Report vulnerabilities privately to: `<SECURITY_CONTACT_EMAIL>`
- Security policy: `<ADD_SECURITY_MD_LINK>`

## License

`<ADD_LICENSE_NAME>`  
See [LICENSE](./LICENSE).

## Star This Project

If this repository helps your hiring or interview workflow, please star it and share it with your team.

