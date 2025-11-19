"""Google OAuth helper (skeleton).

This module should handle OAuth flows to obtain credentials for Gmail and Google Calendar.
Use `google-auth-oauthlib` helpers for web or local flows.
"""
from typing import Any, Dict, Optional
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
except Exception:
    InstalledAppFlow = None  # type: ignore
    Credentials = None  # type: ignore

from llm_email_app.config import settings, BASE_DIR


TOKEN_DIR = Path(BASE_DIR) / 'tokens'
TOKEN_DIR.mkdir(parents=True, exist_ok=True)


def _token_path(name: str) -> Path:
    return TOKEN_DIR / f"{name}_token.json"


def delete_cached_token(name: str = 'google') -> bool:
    """Delete a cached token file for the given name. Returns True if deleted."""
    p = _token_path(name)
    try:
        if p.exists():
            p.unlink()
            return True
    except Exception:
        logger.exception('Failed to delete token file %s', p)
    return False


def run_local_oauth_flow(scopes: list, client_id: Optional[str] = None, client_secret: Optional[str] = None, name: str = 'google') -> Any:
    """Run an installed app local webserver OAuth flow and return credentials.

    - scopes: list of OAuth scopes
    - client_id / client_secret: optional (defaults to env values from `settings`)
    - name: token filename prefix (e.g., 'gmail')

    This will cache tokens to `tokens/{name}_token.json` so subsequent runs are silent.
    If `google-auth-oauthlib` is not installed, raises ImportError.
    """
    if InstalledAppFlow is None:
        raise ImportError("google-auth-oauthlib is required for Google OAuth flow")

    client_id = client_id or settings.GOOGLE_CLIENT_ID
    client_secret = client_secret or settings.GOOGLE_CLIENT_SECRET
    redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', None)

    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment to run OAuth flow")

    token_file = _token_path(name)

    # try to load cached credentials
    if token_file.exists() and Credentials is not None:
        try:
            data = json.loads(token_file.read_text(encoding='utf-8'))
            creds = Credentials.from_authorized_user_info(data, scopes=scopes)
            # refresh if expired
            try:
                from google.auth.transport.requests import Request as _Request  # type: ignore

                if hasattr(creds, 'expired') and creds.expired and creds.refresh_token:
                    creds.refresh(_Request())
            except Exception:
                logger.info('Failed to refresh cached credentials; will start new flow')
            return creds
        except Exception:
            logger.info('Failed to load cached credentials; starting new flow')

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri] if redirect_uri else ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    # run local server; this will open a browser for user consent
    creds = flow.run_local_server(port=8080, prompt='consent')

    # cache token
    try:
        token_file.write_text(creds.to_json(), encoding='utf-8')
    except Exception:
        logger.warning('Unable to write token file; continuing without cache')

    return creds


def refresh_credentials(creds: Any) -> Any:
    """Refresh expired credentials and return updated object."""
    if Credentials is None:
        raise ImportError("google-auth package is required to refresh credentials")
    try:
        if hasattr(creds, 'refresh'):
            from google.auth.transport.requests import Request as _Request  # type: ignore

            creds.refresh(_Request())
        return creds
    except Exception as e:
        raise
