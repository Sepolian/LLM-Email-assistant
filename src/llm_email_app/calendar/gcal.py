"""Google Calendar client implementation.

This client will create events in the user's primary calendar using the Google Calendar API.
It uses `googleapiclient` when available and falls back to a stub when not configured.
"""
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.config import settings


class GCalClient:
    def __init__(self, creds: object = None):
        self.creds = creds
        self.service = None
        if build is None:
            logger.info('googleapiclient not installed; GCalClient will use stubbed create_event')
            return

        try:
            # 只有在提供了 creds 时才构建服务
            # 不自动触发 OAuth flow，应该由调用者（如 GUI）统一处理
            if self.creds:
                self.service = build('calendar', 'v3', credentials=self.creds)
            else:
                # 如果没有提供 creds，不自动触发 OAuth，返回 None service（使用 stubs）
                logger.info('No credentials provided; GCalClient will use stubbed methods')
                self.service = None
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

    def list_events(self, max_results: int = 50, time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get a list of calendar events.
        
        Args:
            max_results: The maximum number of results to return
            time_min: The start time (ISO 8601 format, optional)
            time_max: The end time (ISO 8601 format, optional)
        
        Returns:
            The list of events
        """
        if self.service is None:
            logger.info('GCalClient not configured; returning empty list')
            return []
        
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                maxResults=max_results,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            logger.info('Retrieved %d calendar events', len(events))
            return events
        except HttpError as e:
            logger.exception('Failed to list calendar events: %s', e)
            return []

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get details of a single event.
        
        Args:
            event_id: The ID of the event
        
        Returns:
            The event details, or None if not found
        """
        if self.service is None:
            logger.info('GCalClient not configured; returning None')
            return None
        
        try:
            event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
            return event
        except HttpError as e:
            logger.exception('Failed to get calendar event: %s', e)
            return None

    def update_event(self, event_id: str, updates: Dict[str, Any]) -> Optional[str]:
        """Update a calendar event.
        
        Args:
            event_id: The ID of the event to update
            updates: A dictionary containing the fields to update (e.g., summary, description, start, end, etc.)
        
        Returns:
            The ID of the updated event, or None if failed
        """
        if self.service is None:
            logger.info('GCalClient not configured; cannot update event')
            return None
        
        try:
            # 先获取现有事件
            event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
            
            # 更新字段
            for key, value in updates.items():
                if key == 'title':
                    event['summary'] = value
                elif key == 'notes':
                    event['description'] = value
                elif key == 'start':
                    if isinstance(value, str):
                        event['start'] = {'dateTime': value, 'timeZone': updates.get('timeZone', 'UTC')}
                    else:
                        event['start'] = value
                elif key == 'end':
                    if isinstance(value, str):
                        event['end'] = {'dateTime': value, 'timeZone': updates.get('timeZone', 'UTC')}
                    else:
                        event['end'] = value
                else:
                    event[key] = value
            
            # 保存更新
            updated_event = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event,
                sendUpdates='none'
            ).execute()
            
            logger.info('Updated calendar event id=%s', updated_event.get('id'))
            return updated_event.get('id')
        except HttpError as e:
            logger.exception('Failed to update calendar event: %s', e)
            return None

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event.
        
        Args:
            event_id: The ID of the event to delete
        
        Returns:
            True if successful, False otherwise
        """
        if self.service is None:
            logger.info('GCalClient not configured; cannot delete event')
            return False
        
        try:
            self.service.events().delete(calendarId='primary', eventId=event_id, sendUpdates='none').execute()
            logger.info('Deleted calendar event id=%s', event_id)
            return True
        except HttpError as e:
            logger.exception('Failed to delete calendar event: %s', e)
            return False
