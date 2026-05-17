# Project Structure

## Top-level layout

```text
LLM-Email-assistant/
├── docker-compose.yml
├── Dockerfile
├── frontend/
├── src/llm_email_app/
├── tests/
├── docs/
├── data/          # runtime data, ignored by git
├── tmp/           # runtime state, ignored by git
└── tokens/        # OAuth tokens, ignored by git
```

## Backend package

`src/llm_email_app/` contains the application code:

- `api.py`: FastAPI app and route handlers
- `main.py`: local entry point for `uvicorn`
- `config.py`: environment-driven settings
- `auth/`: Google OAuth helpers and session handling
- `email/`: Gmail integration and rule management
- `calendar/`: Google Calendar integration
- `llm/`: OpenAI-compatible client wrapper
- `agent/`: assistant runtime, persistence, tools, and memory store
- `mcp/`: tool-calling chat helpers
- `demo_fixtures/`: committed mailbox and calendar templates used by demo mode
- `demo_data.py`: official demo script metadata and dynamic fixture generation

## Frontend

The frontend is a static React SPA served directly by FastAPI:

- `index.html`: HTML shell and CDN script loading
- `app.jsx`: router and application state bootstrap
- `pages/`: page-level views
- `i18n/translations.js`: English and Chinese strings

There is no separate Node build pipeline in this repository.

## Tests

`tests/` covers the current backend surfaces:

- demo-mode state and reset behavior
- assistant runtime and resume flows
- API contracts around work items and demo startup
- email triage behavior
- markdown memory persistence

## Generated state

The following locations are created or updated at runtime and should not be hand-edited:

- `data/rules.json`
- `data/memory/`
- `tmp/*.json`
- `tmp/*.sqlite`
- `tokens/google_token.json`
