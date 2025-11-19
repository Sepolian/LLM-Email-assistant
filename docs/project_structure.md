# Project structure

- `app/`
  - `README.md` - quick project overview and run instructions
  - `requirements.txt` - Python dependencies
  - `.env.example` - environment variables template
  - `src/llm_email_app/` - Python package
    - `config.py` - central settings loaded from .env
    - `main.py` - sample runner for the pipeline
    - `llm/openai_client.py` - LLM wrapper (OpenAI format API)
    - `auth/google_oauth.py` - Google OAuth helper (Gmail + Calendar)
    - `email/gmail_client.py` - Gmail fetching and parsing
    - `calendar/gcal.py` - Google Calendar event creation
  - `docs/` - architecture and notes
  - `tests/` - unit tests (pytest)

Next steps (implementation order):
3. Implement OpenAI client and mapping of extracted data to calendar event models.
4. Implement Gmail OAuth and message fetching (with proper parsing for body and attachments).
5. Implement Google Calendar event creation and user confirmation UI/flow.
5. Add tests and CI steps; secure token storage.

