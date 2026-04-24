# Contributing to AI-HR

Thanks for your interest in contributing.

## Prerequisites

- Python 3.10+ (backend)
- Node.js 18+ (frontend)
- `uv` for Python dependency management (recommended)

## Local Setup

### Backend

```bash
cd AI-HR
uv sync
```

### Frontend

```bash
cd frontend
npm install
```

## Development Workflow

1. Fork the repository.
2. Create a branch from `main`.
3. Keep changes focused and atomic.
4. Add or update tests for behavior changes.
5. Open a Pull Request using the PR template.

## Branch Naming

Use one of:

- `feat/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`
- `refactor/<short-description>`
- `test/<short-description>`

## Commit Messages

Prefer conventional style:

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

## Quality Checks

Run before opening a PR:

```bash
cd AI-HR
python -m pytest
```

If your environment includes linters/formatters:

```bash
ruff check ai_hr tests
ruff format ai_hr tests
```

## Pull Request Expectations

- Explain the problem and solution.
- Mention tradeoffs or behavior changes.
- Include test evidence (logs or screenshots).
- Keep PRs reviewable; split large work into smaller PRs.

## Security

- Never commit secrets.
- Use local `.env` files and keep production credentials out of Git.

## Communication

Be respectful and constructive. See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
