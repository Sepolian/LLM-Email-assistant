from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from llm_email_app.agent.state import AgentState, InvocationContext
from llm_email_app.agent.tools.base import AgentTool


def _proposal_payload(args: Dict[str, Any]) -> Dict[str, Any]:
    proposal = dict(args.get("proposal") or {})
    if proposal:
        return proposal
    return {
        "title": args.get("title", ""),
        "start": args.get("start", ""),
        "end": args.get("end", ""),
        "location": args.get("location", ""),
        "attendees": args.get("attendees", []) or [],
        "notes": args.get("notes", ""),
        "timeZone": args.get("timeZone", "Asia/Hong_Kong"),
    }


def build_calendar_tools() -> Dict[str, AgentTool]:
    def list_calendar_events(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gcal_client is None:
            return {"success": False, "error": "Calendar client is not configured"}
        max_results = max(1, min(int(args.get("max_results") or 20), 200))
        time_min = args.get("time_min")
        time_max = args.get("time_max")
        days_ahead = int(args.get("days_ahead") or 14)
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()
        if not time_max:
            time_max = (datetime.now(timezone.utc) + timedelta(days=max(1, days_ahead))).isoformat()
        events = context.gcal_client.list_events(max_results=max_results, time_min=time_min, time_max=time_max)
        return {
            "success": True,
            "events": events,
            "count": len(events),
            "time_min": time_min,
            "time_max": time_max,
        }

    def queue_event_proposal(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        proposal = _proposal_payload(args)
        if not proposal.get("title"):
            return {"success": False, "error": "Proposal title is required"}
        email_payload = state.get("loaded_email") or {}
        email_id = args.get("email_id") or state.get("email_id") or email_payload.get("id") or ""
        email_subject = args.get("email_subject") or email_payload.get("subject") or state.get("email_metadata", {}).get("subject") or ""
        email_summary = args.get("email_summary") or state.get("summary") or ""

        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "proposal": {
                    "id": "shadow-proposal-id",
                    "title": proposal.get("title"),
                    "start": proposal.get("start"),
                    "end": proposal.get("end"),
                    "email_id": email_id,
                },
            }

        if context.proposal_writer is None:
            return {"success": False, "error": "Proposal writer is not configured"}

        entry = context.proposal_writer(
            proposal=proposal,
            email_id=email_id,
            email_subject=email_subject,
            email_summary=email_summary,
        )
        return {
            "success": True,
            "proposal": entry,
        }

    def create_calendar_event(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gcal_client is None:
            return {"success": False, "error": "Calendar client is not configured"}
        proposal = _proposal_payload(args)
        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "event_id": "shadow-event-id",
                "event": proposal,
            }
        event_id = context.gcal_client.create_event(proposal)
        return {
            "success": True,
            "event_id": event_id,
            "event": proposal,
        }

    def update_calendar_event(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gcal_client is None:
            return {"success": False, "error": "Calendar client is not configured"}
        event_id = args.get("event_id")
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        updates = dict(args.get("updates") or {})
        if not updates:
            updates = {key: value for key, value in args.items() if key != "event_id"}
        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "event_id": event_id,
                "updates": updates,
            }
        updated_event_id = context.gcal_client.update_event(event_id, updates)
        return {
            "success": bool(updated_event_id),
            "event_id": updated_event_id or event_id,
            "updates": updates,
        }

    def delete_calendar_event(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gcal_client is None:
            return {"success": False, "error": "Calendar client is not configured"}
        event_id = args.get("event_id")
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "event_id": event_id,
            }
        deleted = context.gcal_client.delete_event(event_id)
        return {
            "success": bool(deleted),
            "event_id": event_id,
        }

    return {
        "list_calendar_events": AgentTool(
            name="list_calendar_events",
            description="List calendar events in a given time range.",
            risk_level="read_only",
            dry_run_supported=True,
            func=list_calendar_events,
        ),
        "queue_event_proposal": AgentTool(
            name="queue_event_proposal",
            description="Save an internal calendar proposal for later user review.",
            risk_level="read_only",
            dry_run_supported=True,
            func=queue_event_proposal,
        ),
        "create_calendar_event": AgentTool(
            name="create_calendar_event",
            description="Create a calendar event.",
            risk_level="external_write",
            dry_run_supported=True,
            func=create_calendar_event,
        ),
        "update_calendar_event": AgentTool(
            name="update_calendar_event",
            description="Update an existing calendar event.",
            risk_level="external_write",
            dry_run_supported=True,
            func=update_calendar_event,
        ),
        "delete_calendar_event": AgentTool(
            name="delete_calendar_event",
            description="Delete an existing calendar event.",
            risk_level="destructive",
            dry_run_supported=True,
            func=delete_calendar_event,
        ),
    }
