"""Google Calendar client implementation.

This client will create events in the user's primary calendar using the Google Calendar API.
It uses `googleapiclient` when available and falls back to a stub when not configured.
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.auth.google_oauth import run_local_oauth_flow
from llm_email_app.config import settings


class GCalClient:
    def __init__(self, creds: object = None):
        self.creds = creds
        self.service = None
        if build is None:
            logger.info('googleapiclient not installed; GCalClient will use stubbed create_event')
            return

        try:
            if not self.creds:
                scopes = ['https://www.googleapis.com/auth/calendar.events']
                # Try to obtain creds via oauth if not provided
                self.creds = run_local_oauth_flow(scopes, name='gcal')
            self.service = build('calendar', 'v3', credentials=self.creds)
        except Exception as e:
            logger.exception('Failed to initialize Google Calendar service: %s', e)
            self.service = None

    def create_event(self, proposal: Dict[str, Any]) -> str:
        """Create an event from a proposal dict and return the created event id.

        proposal expected fields: title, start (ISO), end (ISO), attendees (list of emails), location, notes
        """
        if self.service is None:
            logger.info('GCalClient not configured; returning stub event id')
            return 'gcal-stub-event-id'

        # Build event body
        body: Dict[str, Any] = {
            'summary': proposal.get('title'),
            'description': proposal.get('notes') or '',
        }

        # Start/End
        start = proposal.get('start')
        end = proposal.get('end')
        if start and end:
            body['start'] = {'dateTime': start, 'timeZone': proposal.get('timeZone', 'UTC')}
            body['end'] = {'dateTime': end, 'timeZone': proposal.get('timeZone', 'UTC')}
        else:
            # Fallback: if no times provided, create an all-day event for today
            body['start'] = {'date': proposal.get('date') or '2025-01-01'}
            body['end'] = {'date': proposal.get('date') or '2025-01-02'}

        # Attendees
        attendees = proposal.get('attendees') or []
        if attendees:
            body['attendees'] = [{'email': a} for a in attendees]

        # Location
        if proposal.get('location'):
            body['location'] = proposal.get('location')

        try:
            event = self.service.events().insert(calendarId='primary', body=body, sendUpdates='none').execute()
            event_id = event.get('id')
            logger.info('Created calendar event id=%s', event_id)
            return event_id
        except HttpError as e:
            logger.exception('Failed to create calendar event: %s', e)
            raise
