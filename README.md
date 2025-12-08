# LLM Email — Summary & Calendar Assistant

This project is a Python prototype to summarize emails with LLMs and automatically create calendar events (Google Calendar and Microsoft Outlook via Microsoft Graph).

Features (planned):
- Fetch emails from Gmail (OAuth2)
- Summarize emails and extract scheduling intent using OpenAI-format APIs
- Propose and create calendar events in Google Calendar and Microsoft Graph
- Safe workflow: dry-run, confirmation, conflict detection

Quick start
1. Copy `.env.example` to `.env` and fill credentials for OpenAI, Google OAuth and Microsoft (Azure) app.
2. customize port for the app if you like (defult 8000), also change the `GOOGLE_OAUTH_REDIRECT_URI` port
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


## Docker Compose (run-only, no manual image build required)

Use `docker-compose` to build (if configured) and run the application without manually invoking `docker build`.

Examples (PowerShell):

Start the app (will build images if the compose file includes a `build:` section):

```powershell
docker-compose up -d
```

Start and force rebuild of images (useful after code changes):

```powershell
docker-compose up -d --build --force-recreate
```

Stop and remove containers:

```powershell
docker-compose down
```

Follow logs (all services):

```powershell
docker-compose logs -f
```

Follow logs for a specific service:

```powershell
docker-compose logs -f <service_name>
```

Notes and tips:
- If your `docker-compose.yml` contains a `build:` entry for the backend service, `docker-compose up` will use the repository's `Dockerfile` to build the image automatically — you don't need to run `docker build` separately.
- Use an `.env` file in the repository root for environment variables referenced by `docker-compose.yml`. Some Compose versions also accept `--env-file .env`.
- The compose file typically maps `./data` and `./tokens` to container volumes to persist rules, processed state, and OAuth tokens. Ensure those folders exist and are writable.
- Confirm the exposed ports in `docker-compose.yml` (commonly `8000` for the backend and `3000` for the frontend) and open them in your firewall if required.

## Notes
- This scaffold contains skeleton modules for each integration. None of the integrations are production-ready yet — they contain TODOs and placeholders.
- See `docs/project_structure.md` for architecture and next steps.
- Automation knobs (optional) live in `.env`:
	- `BACKGROUND_REFRESH_INTERVAL_MINUTES` (default `10`) controls how often the backend refreshes cached emails/events and runs the labeling pipeline.
	- `AUTO_LABEL_ENABLED_DEFAULT` (default `false`) defines the initial state of the automation toggle before users change it in Settings.

License: MIT (add your license file)
