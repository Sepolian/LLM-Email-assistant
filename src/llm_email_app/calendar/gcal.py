"""Google Calendar client implementation.

This client will create events in the user's primary calendar using the Google Calendar API.
It uses `googleapiclient` when available and falls back to a stub when not configured.
"""
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.config import settings
from llm_email_app.demo_data import load_demo_calendar_state, save_demo_calendar_state


class GCalClient:
    def __init__(self, creds: object = None):
        self.creds = creds
        self.service = None
        self._demo_mode = bool(settings.DEMO_MODE)
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

    def _is_demo_mode(self) -> bool:
        return self._demo_mode and self.service is None

    def _demo_state(self) -> Dict[str, Any]:
        return load_demo_calendar_state()

    def _save_demo_state(self, payload: Dict[str, Any]) -> None:
        save_demo_calendar_state(payload)

    def _normalize_demo_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        item = dict(event)
        event_id = item.get('id') or f"demo-event-{uuid.uuid4().hex[:10]}"
        summary = item.get('summary') or item.get('title') or 'Untitled event'
        description = item.get('description') or item.get('notes') or ''
        location = item.get('location') or ''
        attendees = item.get('attendees') or []
        start = item.get('start') or {}
        end = item.get('end') or {}
        if isinstance(start, str):
            start = {'dateTime': start}
        if isinstance(end, str):
            end = {'dateTime': end}
        if not start:
            start = {'dateTime': datetime.now(timezone.utc).isoformat()}
        if not end:
            end = dict(start)
        return {
            'id': event_id,
            'summary': summary,
            'description': description,
            'location': location,
            'attendees': attendees,
            'start': start,
            'end': end,
            'status': item.get('status') or 'confirmed',
            'htmlLink': item.get('htmlLink') or f'https://demo.mailflow.local/calendar/{event_id}',
            'updated': item.get('updated') or datetime.now(timezone.utc).isoformat(),
        }

    def _demo_events(self) -> List[Dict[str, Any]]:
        state = self._demo_state()
        events = [self._normalize_demo_event(item) for item in state.get('events', [])]
        events.sort(key=lambda item: (item.get('start') or {}).get('dateTime') or (item.get('start') or {}).get('date') or '')
        return events

    def _persist_demo_events(self, events: List[Dict[str, Any]]) -> None:
        state = self._demo_state()
        state['events'] = events
        self._save_demo_state(state)

    def _parse_filter_time(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            candidate = value.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    def create_event(self, proposal: Dict[str, Any]) -> str:
        """Create an event from a proposal dict and return the created event id.

        proposal expected fields: title, start (ISO), end (ISO), attendees (list of emails), location, notes
        """
        if self._is_demo_mode():
            event = self._normalize_demo_event({
                'summary': proposal.get('title'),
                'description': proposal.get('notes') or '',
                'location': proposal.get('location') or '',
                'attendees': [{'email': a} for a in (proposal.get('attendees') or [])],
                'start': {'dateTime': proposal.get('start'), 'timeZone': proposal.get('timeZone', 'UTC')},
                'end': {'dateTime': proposal.get('end'), 'timeZone': proposal.get('timeZone', 'UTC')},
            })
            events = self._demo_events()
            events.append(event)
            self._persist_demo_events(events)
            return event['id']

        if settings.DRY_RUN:
            logger.info('DRY_RUN enabled; calendar event will not be created: %s', proposal.get('title'))
            return 'gcal-dry-run-event-id'

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
            if self._is_demo_mode():
                min_dt = self._parse_filter_time(time_min)
                max_dt = self._parse_filter_time(time_max)
                filtered: List[Dict[str, Any]] = []
                for event in self._demo_events():
                    start_raw = (event.get('start') or {}).get('dateTime') or (event.get('start') or {}).get('date')
                    end_raw = (event.get('end') or {}).get('dateTime') or (event.get('end') or {}).get('date')
                    start_dt = self._parse_filter_time(start_raw)
                    end_dt = self._parse_filter_time(end_raw) or start_dt
                    if min_dt and end_dt and end_dt < min_dt:
                        continue
                    if max_dt and start_dt and start_dt > max_dt:
                        continue
                    filtered.append(event)
                return filtered[:max_results]
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
            if self._is_demo_mode():
                for event in self._demo_events():
                    if event.get('id') == event_id:
                        return event
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
        if self._is_demo_mode():
            events = self._demo_events()
            next_events: List[Dict[str, Any]] = []
            found = False
            for event in events:
                if event.get('id') != event_id:
                    next_events.append(event)
                    continue
                merged = dict(event)
                for key, value in updates.items():
                    if key == 'title':
                        merged['summary'] = value
                    elif key == 'notes':
                        merged['description'] = value
                    elif key == 'start':
                        merged['start'] = value if isinstance(value, dict) else {'dateTime': value}
                    elif key == 'end':
                        merged['end'] = value if isinstance(value, dict) else {'dateTime': value}
                    else:
                        merged[key] = value
                merged['updated'] = datetime.now(timezone.utc).isoformat()
                next_events.append(self._normalize_demo_event(merged))
                found = True
            if found:
                self._persist_demo_events(next_events)
                return event_id
            return None

        if settings.DRY_RUN:
            logger.info('DRY_RUN enabled; calendar event %s will not be updated: %s', event_id, updates)
            return event_id

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
        if self._is_demo_mode():
            events = self._demo_events()
            next_events = [event for event in events if event.get('id') != event_id]
            if len(next_events) == len(events):
                return False
            self._persist_demo_events(next_events)
            return True

        if settings.DRY_RUN:
            logger.info('DRY_RUN enabled; calendar event %s will not be deleted', event_id)
            return True

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
