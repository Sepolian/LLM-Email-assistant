# MailFlow Demo

MailFlow Demo is a FastAPI and React application for exploring email and calendar workflows with a chat-driven assistant. It supports live Google OAuth for Gmail and Google Calendar, and it also includes a self-contained demo mode with local mailbox and calendar fixtures for quick setup.

## What it includes

- inbox browsing, search, summaries, drafts, and label rules
- calendar listing, event creation, updates, and deletion
- chat-driven tool use for email and calendar tasks
- threaded demo scenarios with pending work items and timeline playback
- local markdown-based memory storage for assistant context

## Repository layout

- `src/llm_email_app/` backend package
- `frontend/` React SPA served by FastAPI
- `docs/` architecture, API, and demo documentation
- `tests/` backend and runtime tests
- `src/llm_email_app/demo_fixtures/` committed demo mailbox and calendar seeds

## Quick start

1. Copy `.env.example` to `.env`.
2. Fill `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_API_BASE` for your LLM endpoint.
3. For live Gmail and Calendar access, also fill the Google OAuth variables.
4. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Start the app:

```bash
PYTHONPATH=src python -m llm_email_app.main
```

Open `http://localhost:8000`.

## Demo mode

Demo mode skips Google login and loads a local mailbox plus calendar state from committed fixtures. Resetting the demo regenerates dates relative to the current server time, or to `DEMO_REFERENCE_TIME` when that variable is set.

Built-in demo threads:

- resolve a meeting conflict and draft the follow-up reply
- show the next 7 days of calendar events
- search for a budget email and summarize it

Recommended `.env` settings for demo mode:

```env
DRY_RUN=true
DEMO_MODE=true
AGENT_ENABLED=true
OPENAI_API_KEY=...
OPENAI_API_BASE=http://your-openai-compatible-endpoint
OPENAI_MODEL=your-model
```

Optional fixed demo clock:

```env
DEMO_REFERENCE_TIME=2026-05-17T09:00:00+08:00
```

## Docker

Build and run with Docker Compose:

```bash
docker compose up -d --build
```

Stop the stack:

```bash
docker compose down
```

The compose file mounts `data/`, `tmp/`, and `tokens/` so local state persists across container restarts.
Compose variable substitution reads from `.env`, and the backend now receives the demo-related variables from that file.

## Tests

Run the backend test suite with:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q tests
```

Current tests cover demo mode, chat/runtime flows, work-item resumption, email triage, and markdown memory storage.

## Documentation

- `docs/architecture.md`
- `docs/demo.md`
- `docs/api.md`
- `docs/project_structure.md`

## Notes

- `docker-compose.yml` enables `DEMO_MODE=true` by default for a faster first run.
- The frontend is served directly by FastAPI from `frontend/`; no separate Node build step is required.
- Legacy proposal and approval endpoints still exist in the backend, but the main demo flow uses threads, work items, and timelines.

## Demo preview

<img width="1103" height="1254" alt="image" src="https://github.com/user-attachments/assets/82f97d6b-f348-4ce6-8812-02fa70997c11" />
<img width="1083" height="1289" alt="image" src="https://github.com/user-attachments/assets/9e3daf2e-f80a-4ed4-aa34-4a2f89a03850" />
