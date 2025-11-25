"""Google OAuth helper (skeleton).

This module should handle OAuth flows to obtain credentials for Gmail and Google Calendar.
Use `google-auth-oauthlib` helpers for web or local flows.
"""
from typing import Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
except Exception:
    Flow = None  # type: ignore
    Credentials = None  # type: ignore

from llm_email_app.config import settings, BASE_DIR


TOKEN_DIR = Path(BASE_DIR) / 'tokens'
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# 统一使用 'google' 作为 token 文件名，支持 Gmail 和 GCal
DEFAULT_TOKEN_NAME = 'google'

# Default OAuth scopes required by the app. Include gmail.modify so delete/archive work.
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def get_web_flow(scopes: list = None) -> Any:
    """Create a Google OAuth Flow for a web application."""
    if Flow is None:
        raise ImportError("google-auth-oauthlib is required for Google OAuth flow")

    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')

    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment to run OAuth flow")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    
    if scopes is None:
        scopes = DEFAULT_SCOPES

    flow = Flow.from_client_config(client_config, scopes=scopes, redirect_uri=redirect_uri)
    return flow
