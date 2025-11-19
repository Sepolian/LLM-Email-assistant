"""Microsoft Graph calendar helper (skeleton).

Implement event creation via Microsoft Graph once tokens are available.
"""
from typing import Dict, Any


class MSGraphCalendarClient:
    def __init__(self, token: str = None):
        self.token = token

    def create_event(self, event: Dict[str, Any]) -> str:
        """Create event in user's primary calendar and return event id (stub)."""
        # TODO: call Microsoft Graph /me/events with proper Authorization header
        return 'ms-graph-stub-event-id'
