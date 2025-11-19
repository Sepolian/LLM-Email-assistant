"""Gmail client skeleton.

Replace stubs with real Gmail API calls using googleapiclient.discovery or the Gmail REST endpoints with authorized credentials.
"""
from typing import List, Dict, Optional
import base64
import email as py_email
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.config import settings
from llm_email_app.auth.google_oauth import run_local_oauth_flow


class GmailClient:
    """Gmail client that uses Google APIs when configured, otherwise falls back to stubs.

    Behavior:
    - If `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are present in env/.env, try to run OAuth flow
      and build a Gmail service.
    - If google API libs are not installed or env vars missing, return stubbed emails (for local dev).
    """

    def __init__(self, creds: object = None):
        self.creds = creds
        self.service = None
        if build is None:
            logger.info('googleapiclient not installed; GmailClient will return stubbed emails')
            return

        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            logger.info('Google client id/secret not configured; GmailClient will return stubbed emails')
            return

        try:
            scopes = ['https://www.googleapis.com/auth/gmail.readonly']
            creds = creds or run_local_oauth_flow(scopes, name='gmail')
            self.creds = creds
            self.service = build('gmail', 'v1', credentials=creds)
        except Exception as e:
            logger.exception('Failed to initialize Gmail service; falling back to stubs: %s', e)
            self.service = None

    def _parse_message(self, msg: dict) -> Dict[str, str]:
        """Parse a Gmail API message resource into a simple dict with id, from, subject, body."""
        headers = {h['name']: h.get('value') for h in msg.get('payload', {}).get('headers', [])}
        from_hdr = headers.get('From') or headers.get('From:') or ''
        subject = headers.get('Subject') or ''

        body = ''
        payload = msg.get('payload', {})
        if 'parts' in payload:
            # walk parts to find text/plain
            for part in payload.get('parts', []):
                mime = part.get('mimeType', '')
                if mime == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')
                        break
                # fallback to first part
            if not body:
                # try first part payload
                first = payload.get('parts', [])[0]
                data = first.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')
        else:
            data = payload.get('body', {}).get('data')
            if data:
                body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')

        # simple cleanup: if body seems to be raw email, parse and extract payload
        if body and '\n\n' in body and 'From:' in body[:200]:
            try:
                parsed = py_email.message_from_string(body)
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == 'text/plain':
                            body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                            break
                else:
                    body = parsed.get_payload(decode=True).decode(parsed.get_content_charset() or 'utf-8', errors='replace')
            except Exception:
                pass

        # try to extract receive/internal date (milliseconds since epoch)
        received = None
        try:
            internal = msg.get('internalDate') or msg.get('internal_date')
            if internal:
                # internalDate is milliseconds since epoch
                ts = int(internal) / 1000.0
                received = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            received = None

        return {'id': msg.get('id'), 'from': from_hdr, 'subject': subject, 'body': body, 'received': received}

    def fetch_recent_emails(self, max_results: int = 5) -> List[Dict]:
        """Return a list of recent emails in simplified dict form.

        Each item: {'id': str, 'from': str, 'subject': str, 'body': str}
        """
        # If service missing (libs or config), return stubs for dev
        if self.service is None:
            return [
                {
                    'id': 'stub-1',
                    'from': 'alice@example.com',
                    'subject': 'Meeting request: Q4 roadmap',
                    'body': 'Hi, can we meet next Tuesday at 10am to go over the Q4 roadmap? Regards, Alice'
                },
                {
                    'id': 'stub-2',
                    'from': 'bob@example.com',
                    'subject': 'Quick sync',
                    'body': "Can we do a quick sync tomorrow afternoon?"
                }
            ][:max_results]

        try:
            resp = self.service.users().messages().list(userId='me', maxResults=max_results).execute()
            msgs = resp.get('messages', [])
            results = []
            for m in msgs:
                mid = m.get('id')
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)
            return results
        except HttpError as e:
            logger.exception('Gmail API error: %s', e)
            # fallback to stubs on API error
            return [
                {
                    'id': 'stub-1',
                    'from': 'alice@example.com',
                    'subject': 'Meeting request: Q4 roadmap',
                    'body': 'Hi, can we meet next Tuesday at 10am to go over the Q4 roadmap? Regards, Alice'
                }
            ]

    def fetch_emails_since(self, days: int = 7, max_results: Optional[int] = None) -> List[Dict]:
        """Fetch emails from the authenticated user's mailbox from the past `days` days.

        If not authenticated, returns the same stubbed emails as `fetch_recent_emails`.
        """
        # If service missing, return stubs
        if self.service is None:
            return self.fetch_recent_emails(max_results=max_results or 5)

        # Gmail search operator 'newer_than:Xd' is convenient
        q = f'newer_than:{days}d'
        try:
            req = self.service.users().messages().list(userId='me', q=q)
            if max_results:
                req = self.service.users().messages().list(userId='me', q=q, maxResults=max_results)
            resp = req.execute()
            msgs = resp.get('messages', [])
            results = []
            for m in msgs:
                mid = m.get('id')
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)
            return results
        except HttpError as e:
            logger.exception('Gmail API error while fetching by time: %s', e)
            return self.fetch_recent_emails(max_results=max_results or 5)
