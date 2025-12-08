# Project Structure

This document outlines the structure and architecture of the LLM Email Assistant.

## Directory Overview

- `README.md` - Top-level overview and setup guide.
- `.env` - Environment variables for API keys and app configuration.
- `requirements.txt` - Python backend dependencies.
- `data/`
  - `rules.json` - Persistence file for user-defined auto-labeling rules.
- `docs/` - Documentation files (`project_structure.md`, `todo.md`).
- `frontend/` - React single-page app.
  - `index.html` - Root document served to the browser.
  - `app.jsx` - SPA bootstrap and router.
  - `pages/` - Routed views (`Home.jsx`, `Email.jsx`, `Calendar.jsx`, `Settings.jsx`, `Chat.jsx`).
  - `i18n/` - Localization files for multilingual support.
- `src/llm_email_app/` - Backend Python package.
  - `config.py` - Environment-driven configuration.
  - `main.py` - Entry point for the FastAPI app.
  - `api.py` - FastAPI route definitions and background tasks.
  - `auth/` - Google OAuth helpers (`google_oauth.py`, `session.py`).
  - `email/` - Gmail integration.
    - `gmail_client.py` - Gmail API wrapper.
    - `rules.py` - Rule engine for auto-labeling.
  - `calendar/` - Google Calendar client (`gcal.py`).
  - `llm/` - LLM adapters (`openai_client.py`).
  - `mcp/` - Modular Command Processor for email and calendar tools.
- `tmp/` - Runtime temporary files (e.g., cached emails, calendar events).
- `tokens/` - OAuth token storage (`google_token.json`).

## Architecture & Key Modules

### Backend (FastAPI)
- **API (`api.py`)**: Handles frontend requests, manages background tasks (email/calendar refresh), and orchestrates the auto-labeling pipeline.
- **Authentication (`auth/`)**: Manages Google OAuth flow. Tokens are stored in `tokens/`.
- **LLM Client (`llm/openai_client.py`)**: Wraps OpenAI API calls. Provides methods for:
  - `summarize_email`: Generates summaries and extracts event proposals.
  - `evaluate_label_rules`: Matches emails against user-defined rules using the LLM.
- **Email Integration (`email/`)**:
  - `gmail_client.py`: Handles Gmail API interactions (e.g., fetching emails, creating drafts).
  - `rules.py`: Implements `RuleManager` to load/save rules from `data/rules.json`.
- **Calendar Integration (`calendar/`)**:
  - `gcal.py`: Handles Google Calendar API interactions (e.g., creating events, fetching schedules).
- **Automation**:
  - Background tasks for auto-labeling and event extraction.
  - Tracks processed emails and proposals in `tmp/`.

### Frontend (React)
- **SPA Architecture**: Uses `app.jsx` for routing.
- **State Management**: Uses `useState` and `useEffect` for data fetching. Caches email lists and calendar events to minimize API calls.
- **Views**:
  - **Home**: System overview and automation logs.
  - **Email**: Inbox view with summarization and folder navigation.
  - **Calendar**: Monthly view of events.
  - **Settings**: Manage automation rules and settings.
  - **Chat**: Interactive assistant for scheduling and email queries.

### Auto-Labeling System
- **Rule Engine (`email/rules.py`)**:
  - Loads and saves rules from `data/rules.json`.
  - Evaluates emails against rules using `OpenAIClient.evaluate_label_rules`.
- **Workflow**:
  1. **Trigger**: Runs on a schedule (background loop) or manually via Settings.
  2. **Evaluation**: Fetches recent emails and checks them against active rules.
  3. **LLM Analysis**: Uses OpenAI to determine if an email matches a rule's criteria.
  4. **Action**: Applies labels to matching emails using `GmailClient`.
  5. **State Tracking**: Tracks processed emails in `tmp/auto_label_processed.json`.

## Key Features
- **Email Summarization**: Summarizes email content and extracts actionable insights.
- **Event Proposals**: Extracts scheduling intents from emails and proposes calendar events.
- **Automation**: Auto-labels emails and adds events to the calendar.
- **User-defined Rules**: Allows users to define custom rules for email labeling.

## Next Steps
- Add more robust error handling and logging.
- Enhance the UI for better user experience.
- Expand integration to support Microsoft Outlook and other email/calendar platforms.


