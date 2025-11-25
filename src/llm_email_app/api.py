import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import logging
import calendar as cal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from llm_email_app.auth.session import login, auth_callback, get_credentials
from llm_email_app.config import settings, BASE_DIR
from llm_email_app.email.gmail_client import GmailClient
from llm_email_app.calendar.gcal import GCalClient
from typing import Dict, Any, List, Optional, Tuple
from llm_email_app.auth.google_oauth import TOKEN_DIR
import json

logger = logging.getLogger(__name__)

TMP_DIR = (BASE_DIR / 'tmp')
TMP_DIR.mkdir(parents=True, exist_ok=True)
EMAIL_CACHE_PATH = TMP_DIR / 'emails_recent.json'
CALENDAR_CACHE_PATH = TMP_DIR / 'calendar_recent.json'


def _coerce_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Support both Z suffix and explicit offsets
        if value.endswith('Z'):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        if 'T' in value and '+' not in value and value.count('-') <= 2:
            return datetime.fromisoformat(value + '+00:00')
        if 'T' not in value:
            return datetime.fromisoformat(f"{value}T00:00:00+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _write_temp_json(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        logger.warning('Unable to persist snapshot at %s: %s', path, exc)


def _persist_recent_emails(mailbox: Dict[str, Any], window_days: int = 14) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    flattened: List[Dict[str, Any]] = []
    for folder_key, payload in mailbox.get('folders', {}).items():
        for item in payload.get('items', []):
            received = _coerce_datetime(item.get('received'))
            if received is None or received >= cutoff:
                enriched = dict(item)
                enriched['folder'] = folder_key
                flattened.append(enriched)

    snapshot = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'window_days': window_days,
        'count': len(flattened),
        'emails': flattened,
    }
    _write_temp_json(EMAIL_CACHE_PATH, snapshot)


def _persist_calendar(events: List[Dict[str, Any]], window_days: int = 365) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    filtered: List[Dict[str, Any]] = []
    todos: List[Dict[str, Any]] = []
    for event in events:
        start = event.get('start', {}) or {}
        start_raw = start.get('dateTime') or start.get('date')
        start_dt = _coerce_datetime(start_raw)
        if start_dt is None or start_dt >= cutoff:
            filtered.append(event)
            summary = (event.get('summary') or '').lower()
            if event.get('eventType') == 'task' or 'todo' in summary:
                todos.append(event)

    snapshot = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'window_days': window_days,
        'events': filtered,
        'todos': todos,
    }
    _write_temp_json(CALENDAR_CACHE_PATH, snapshot)


def _month_bounds(month_str: str) -> Tuple[datetime, datetime]:
    try:
        year, month = map(int, month_str.split('-'))
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = cal.monthrange(year, month)[1]
        last = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        return first, last
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid month format, expected YYYY-MM") from exc


app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

app.add_route("/login", route=login, methods=["GET"])
app.add_route("/auth/callback", route=auth_callback, methods=["GET"])

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    token_file = TOKEN_DIR / "google_token.json"
    if token_file.exists():
        token_file.unlink()
    return RedirectResponse(url="/")

@app.get("/user", response_model=Dict[str, Any])
async def get_user(request: Request):
    user = request.session.get("user")
    if user:
        return JSONResponse(user)

    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if 'id_token' in creds_json:
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            from llm_email_app.auth.google_oauth import get_web_flow

            flow = get_web_flow()
            id_info = id_token.verify_oauth2_token(
                creds_json['id_token'], google_requests.Request(), flow.client_config["client_id"]
            )
            user = {
                "name": id_info.get("name"),
                "email": id_info.get("email"),
                "picture": id_info.get("picture"),
            }
            request.session["user"] = user
            return JSONResponse(user)
        except Exception as e:
            print(e) # log error
            raise HTTPException(status_code=401, detail="Could not verify user.")

    raise HTTPException(status_code=401, detail="User information not available.")

def get_gmail_client(request: Request) -> GmailClient:
    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")
    creds = Credentials.from_authorized_user_info(creds_json)
    return GmailClient(creds=creds)

def get_gcal_client(request: Request) -> GCalClient:
    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")
    creds = Credentials.from_authorized_user_info(creds_json)
    return GCalClient(creds=creds)

@app.get("/")
def read_root():
    return FileResponse('frontend/index.html')

@app.get("/emails", response_model=Dict[str, Any])
def get_emails(
    gmail_client: GmailClient = Depends(get_gmail_client), 
    page: int = 1, 
    per_page: int = 20,
    days: int = 7,
    folder: str = 'inbox'
):
    capped_per_page = min(per_page, 20)
    normalized_folder = (folder or 'inbox').lower()
    mailbox = gmail_client.fetch_mailbox_overview(
        active_folder=normalized_folder,
        page=page,
        per_page=capped_per_page,
        days=days
    )
    _persist_recent_emails(mailbox, window_days=14)
    return mailbox

@app.get("/emails/search", response_model=List[Dict[str, Any]])
def search_emails(q: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    # This is a placeholder, as the original gmail_client did not have a generic search function.
    # We will implement this later.
    return []

@app.post("/emails/send")
def send_email(email_data: Dict[str, Any], gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.send_email(
        to=email_data["to"],
        subject=email_data["subject"],
        body=email_data["body"],
        cc=email_data.get("cc"),
        bcc=email_data.get("bcc"),
    )

@app.post("/emails/{message_id}/reply")
def reply_to_email(message_id: str, body: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.reply_to_email(message_id=message_id, body=body)

@app.delete("/emails/{message_id}")
def delete_email(message_id: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.delete_email(message_id=message_id)

@app.post("/emails/{message_id}/read")
def mark_email_as_read(message_id: str, read: bool = True, gmail_client: GmailClient = Depends(get_gmail_client)):
    return {"success": gmail_client.mark_as_read(message_id=message_id, read=read)}

@app.post("/emails/{message_id}/archive")
def archive_email(message_id: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return {"success": gmail_client.archive_email(message_id=message_id)}

@app.get("/calendar/events", response_model=List[Dict[str, Any]])
def get_calendar_events(
    gcal_client: GCalClient = Depends(get_gcal_client),
    max_results: int = 200,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    month: Optional[str] = None,
):
    now = datetime.now(timezone.utc)

    if month:
        start, end = _month_bounds(month)
        time_min = start.isoformat()
        time_max = end.isoformat()
    else:
        if not time_min:
            time_min = now.isoformat()
        if not time_max:
            time_max = (now + timedelta(days=365)).isoformat()

    events = gcal_client.list_events(max_results=max_results, time_min=time_min, time_max=time_max)

    snapshot_events = events
    if gcal_client.service is not None:
        snapshot_events = gcal_client.list_events(
            max_results=max(max_results, 500),
            time_min=(now - timedelta(days=365)).isoformat(),
            time_max=(now + timedelta(days=365)).isoformat(),
        )

    _persist_calendar(snapshot_events, window_days=365)
    return events

@app.post("/calendar/events", response_model=Dict[str, str])
def create_calendar_event(proposal: Dict[str, Any], gcal_client: GCalClient = Depends(get_gcal_client)):
    event_id = gcal_client.create_event(proposal)
    return {"event_id": event_id}

@app.get("/calendar/events/{event_id}", response_model=Optional[Dict[str, Any]])
def get_calendar_event(event_id: str, gcal_client: GCalClient = Depends(get_gcal_client)):
    event = gcal_client.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@app.put("/calendar/events/{event_id}", response_model=Dict[str, str])
def update_calendar_event(event_id: str, updates: Dict[str, Any], gcal_client: GCalClient = Depends(get_gcal_client)):
    updated_event_id = gcal_client.update_event(event_id, updates)
    if not updated_event_id:
        raise HTTPException(status_code=404, detail="Event not found or update failed")
    return {"event_id": updated_event_id}

@app.delete("/calendar/events/{event_id}", response_model=Dict[str, bool])
def delete_calendar_event(event_id: str, gcal_client: GCalClient = Depends(get_gcal_client)):
    if not gcal_client.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found or delete failed")
    return {"success": True}
