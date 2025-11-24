import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from llm_email_app.auth.session import login, auth_callback, get_credentials
from llm_email_app.config import settings
from llm_email_app.email.gmail_client import GmailClient
from llm_email_app.calendar.gcal import GCalClient
from typing import Dict, Any, List, Optional
from llm_email_app.auth.google_oauth import TOKEN_DIR
import json

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

@app.get("/emails", response_model=List[Dict[str, Any]])
def get_emails(
    gmail_client: GmailClient = Depends(get_gmail_client), 
    page: int = 1, 
    per_page: int = 20,
    days: int = 7
):
    return gmail_client.fetch_recent_emails(
        page=page, 
        per_page=per_page,
        days=days
    )

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
    max_results: int = 50,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
):
    return gcal_client.list_events(max_results=max_results, time_min=time_min, time_max=time_max)

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
