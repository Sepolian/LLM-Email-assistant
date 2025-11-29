# LLM Email — Summary & Calendar Assistant

This project is a Python prototype to summarize emails with LLMs and automatically create calendar events (Google Calendar and Microsoft Outlook via Microsoft Graph).

Features (planned):
- Fetch emails from Gmail (OAuth2)
- Summarize emails and extract scheduling intent using OpenAI-format APIs
- Propose and create calendar events in Google Calendar and Microsoft Graph
- Safe workflow: dry-run, confirmation, conflict detection

Quick start
1. Copy `.env.example` to `.env` and fill credentials for OpenAI, Google OAuth and Microsoft (Azure) app.
2. customize port for the app if you like (defult 8000)
3. Create a Python virtual env and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Run the sample pipeline:

Launch GUI with:

```powershell
$env:PYTHONPATH='src'; python -m src.llm_email_app.main
```
GUI at http://localhost:8000/

The GUI lists recent emails (stubs by default), lets you summarize selected emails using the LLM client (stub if no API key), shows proposed events, and allows creating events (respects the `DRY_RUN` flag in `.env`).

Notes
- This scaffold contains skeleton modules for each integration. None of the integrations are production-ready yet — they contain TODOs and placeholders.
- See `docs/project_structure.md` for architecture and next steps.
- Automation knobs (optional) live in `.env`:
	- `BACKGROUND_REFRESH_INTERVAL_MINUTES` (default `10`) controls how often the backend refreshes cached emails/events and runs the labeling pipeline.
	- `AUTO_LABEL_ENABLED_DEFAULT` (default `false`) defines the initial state of the automation toggle before users change it in Settings.

License: MIT (add your license file)
