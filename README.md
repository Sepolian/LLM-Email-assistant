# LLM Email — Summary & Calendar Assistant

This project is a Python prototype to summarize emails with LLMs and automatically create calendar events (Google Calendar and Microsoft Outlook via Microsoft Graph).

Features (planned):
- Fetch emails from Gmail (OAuth2)
- Summarize emails and extract scheduling intent using OpenAI-format APIs
- Propose and create calendar events in Google Calendar and Microsoft Graph
- Safe workflow: dry-run, confirmation, conflict detection

Quick start
1. Copy `.env.example` to `.env` and fill credentials for OpenAI, Google OAuth and Microsoft (Azure) app.
2. Create a Python virtual env and install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Run the sample pipeline (dry-run):

```powershell
python -m llm_email_app.main
```

Simple GUI for testing

There's a light Tkinter GUI for quick manual testing. Launch it with:

```powershell
# from project `app` folder
$env:PYTHONPATH='src'; python -m llm_email_app.gui
```

The GUI lists recent emails (stubs by default), lets you summarize selected emails using the LLM client (stub if no API key), shows proposed events, and allows creating events (respects the `DRY_RUN` flag in `.env`).

Notes
- This scaffold contains skeleton modules for each integration. None of the integrations are production-ready yet — they contain TODOs and placeholders.
- See `docs/project_structure.md` for architecture and next steps.

License: MIT (add your license file)
