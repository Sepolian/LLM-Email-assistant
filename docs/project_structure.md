# Project structure

- `README.md` - top-level overview and combined setup guide
- `requirements.txt` - Python backend dependencies
- `data/`
  - `rules.json` - persistence file for user-defined auto-labeling rules
- `docs/` - additional notes (`project_structure.md`, `todo.md`)
- `frontend/` - React single-page app
  - `index.html` - root document served to the browser
  - `app.jsx` - SPA bootstrap and router
  - `pages/` - routed views (`Home.jsx`, `Email.jsx`, `Calendar.jsx`, `Settings.jsx`)
- `src/llm_email_app/` - backend Python package
  - `config.py` - environment-driven configuration (hard coded env variable if not set in .env)
  - `main.py` - entry point for the FastAPI app
  - `api.py` - FastAPI route definitions
  - `auth/` - Google OAuth helpers (`google_oauth.py`, `session.py`)
  - `email/` - Gmail integration
    - `gmail_client.py` - Gmail API wrapper
    - `rules.py` - Rule engine for auto-labeling
  - `calendar/` - Google Calendar client (`gcal.py`)
  - `llm/` - LLM adapters (`openai_client.py`)
- `tmp/` - runtime temporary files (caches for emails, calendar, processed state)
- `tokens/` - runtime token cache (`google_token.json`)

## Architecture & Key Modules

### Backend (FastAPI)
- **API (`api.py`):** Handles frontend requests, manages background tasks (email/calendar refresh), and orchestrates the auto-labeling pipeline.
- **Authentication (`auth/`):** Manages Google OAuth flow. Tokens are stored in `tokens/`.
- **LLM Client (`llm/openai_client.py`):** Wraps OpenAI API calls. Provides methods for:
  - `summarize_email`: Generates summaries and extracts event proposals.
  - `evaluate_label_rules`: Matches emails against user-defined rules using the LLM.

### Auto-Labeling System
- **Rule Engine (`email/rules.py`):** Implements `RuleManager` to load/save rules from `data/rules.json`.
- **Workflow:**
  1. **Trigger:** Runs on a schedule (background loop) or manually via Settings.
  2. **Evaluation:** Fetches recent emails and checks them against active rules.
  3. **LLM Analysis:** Uses `OpenAIClient.evaluate_label_rules` to determine if an email matches a rule's criteria (based on sender, subject, body).
  4. **Action:** If a match is found, `GmailClient` ensures the label exists and applies it to the message.
  5. **State:** Tracks processed emails in `tmp/auto_label_processed.json` to avoid redundant processing.

### Frontend (React)
- **SPA Architecture:** Uses `app.jsx` for routing.
- **State Management:** Uses `useState` and `useEffect` for data fetching. Caches email lists and calendar events to minimize API calls.
- **Views:**
  - **Home:** System overview and automation logs.
  - **Email:** Inbox view with summarization and folder navigation.
  - **Calendar:** Monthly view of events.


