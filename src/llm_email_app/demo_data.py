from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from llm_email_app.config import settings


DEFAULT_DEMO_USER = {
    "name": "Avery Chen",
    "email": "avery.chen@demo.mailflow.local",
    "picture": None,
    "demo_mode": True,
}

OFFICIAL_DEMO_SCRIPTS = [
    {
        "script_id": "flagship_conflict",
        "thread_id": "demo-flagship-conflict",
        "thread_kind": "official",
        "title": "Client launch conflict resolution",
        "thread_title": "Client launch rehearsal conflict",
        "starter_message": "Handle the client launch rehearsal email and resolve the scheduling conflict.",
        "scenario_id": "client_launch_conflict",
        "demo_role": "flagship",
    },
    {
        "script_id": "show_schedule",
        "thread_id": "demo-show-schedule",
        "thread_kind": "official",
        "title": "Show my schedule",
        "thread_title": "Upcoming schedule overview",
        "starter_message": "Show my schedule for the next 7 days.",
        "scenario_id": "schedule_overview",
        "demo_role": "support",
    },
    {
        "script_id": "search_and_summarize",
        "thread_id": "demo-search-summarize",
        "thread_kind": "official",
        "title": "Search and summarize email",
        "thread_title": "Budget email summary",
        "starter_message": "Search emails about budget and summarize the most relevant one.",
        "scenario_id": "budget_summary",
        "demo_role": "support",
    },
]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _parse_reference_time(raw_value: str) -> datetime | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_local_timezone())
    return parsed


def demo_reference_now() -> datetime:
    return _parse_reference_time(settings.DEMO_REFERENCE_TIME) or datetime.now().astimezone()


def _in_timezone(reference: datetime, tz_name: str) -> datetime:
    return reference.astimezone(ZoneInfo(tz_name))


def _scheduled_at(reference: datetime, tz_name: str, days_offset: int, hour: int, minute: int) -> datetime:
    local = _in_timezone(reference, tz_name)
    target_date = local.date() + timedelta(days=days_offset)
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=ZoneInfo(tz_name),
    )


def _received_at(reference: datetime, tz_name: str, *, days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    local = _in_timezone(reference, tz_name)
    return local - timedelta(days=days, hours=hours, minutes=minutes)


def _date_text(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def _time_text(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def _event_window(reference: datetime) -> Dict[str, datetime]:
    tz_name = "Asia/Hong_Kong"
    conflict_start = _scheduled_at(reference, tz_name, 3, 15, 0)
    return {
        "launch_standup_start": _scheduled_at(reference, tz_name, 2, 9, 30),
        "launch_standup_end": _scheduled_at(reference, tz_name, 2, 10, 0),
        "conflict_start": conflict_start,
        "conflict_end": _scheduled_at(reference, tz_name, 3, 15, 45),
        "rehearsal_end": _scheduled_at(reference, tz_name, 3, 15, 30),
        "budget_review_start": _scheduled_at(reference, tz_name, 7, 10, 0),
        "budget_review_end": _scheduled_at(reference, tz_name, 7, 11, 0),
        "offsite_start": _scheduled_at(reference, tz_name, 10, 0, 0),
        "offsite_end": _scheduled_at(reference, tz_name, 11, 0, 0),
        "hiring_panel_start": _scheduled_at(reference, tz_name, 5, 11, 30),
        "flight_hold_start": _scheduled_at(reference, tz_name, 10, 9, 20),
    }


def _build_demo_mailbox_seed(template_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(template_payload or {}))
    payload.setdefault("user", dict(DEFAULT_DEMO_USER))
    payload.setdefault("labels", [])
    payload.setdefault("messages", [])

    reference = demo_reference_now()
    windows = _event_window(reference)
    by_id = {str(item.get("id") or ""): item for item in payload.get("messages", [])}

    flagship = by_id.get("demo-inbox-client-launch")
    if flagship:
        tz_name = "Asia/Hong_Kong"
        start = windows["conflict_start"]
        end = windows["rehearsal_end"]
        received = _received_at(reference, tz_name, hours=2)
        flagship["event_request"] = {
            **dict(flagship.get("event_request") or {}),
            "title": "Client launch rehearsal",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeZone": tz_name,
            "location": "Zoom",
            "notes": "30-minute rehearsal with design and ops leads.",
            "attendees": ["maya@northstarstudios.co"],
        }
        flagship["subject"] = f"Need confirmation: client launch rehearsal on {_date_text(start)} at {_time_text(start)}"
        flagship["body"] = (
            "Hi Avery,\n\n"
            f"Can you confirm the client launch rehearsal on {_date_text(start)} at {_time_text(start)} {start.tzname()}? "
            "We'll use Zoom and need 30 minutes with the design and ops leads.\n\n"
            "Please reply if you want me to move it.\n\n"
            "Thanks,\nMaya"
        )
        flagship["snippet"] = (
            f"Can you confirm the client launch rehearsal on {_date_text(start)} at {_time_text(start)} {start.tzname()}?"
        )
        flagship["received"] = received.isoformat()

    budget = by_id.get("demo-inbox-budget")
    if budget:
        start = windows["budget_review_start"]
        received = _received_at(reference, "Asia/Hong_Kong", hours=3, minutes=10)
        budget["subject"] = "Budget review follow-up and requested reply"
        budget["body"] = (
            "Avery,\n\n"
            f"Please send me a reply draft today confirming whether you can join the budget review on {_date_text(start)} "
            f"at {_time_text(start)} {start.tzname()}. If that time works, I will send the final agenda.\n\n"
            "Jordan"
        )
        budget["snippet"] = (
            f"Please send me a reply draft today confirming whether you can join the budget review on {_date_text(start)} "
            f"at {_time_text(start)} {start.tzname()}."
        )
        budget["received"] = received.isoformat()

    travel = by_id.get("demo-inbox-travel")
    if travel:
        flight = windows["flight_hold_start"]
        received = _received_at(reference, "Asia/Hong_Kong", days=1, hours=4)
        travel["subject"] = f"Flight held for Shenzhen offsite on {_date_text(flight)}"
        travel["body"] = (
            "Hi Avery,\n\n"
            f"I've placed a 24-hour hold on your {_date_text(flight)} {_time_text(flight)} flight to Shenzhen for the product offsite. "
            "Please confirm if you want me to ticket it.\n\n"
            "Best,\nLena"
        )
        travel["snippet"] = (
            f"I've placed a 24-hour hold on your {_date_text(flight)} {_time_text(flight)} flight to Shenzhen for the product offsite."
        )
        travel["received"] = received.isoformat()

    hiring = by_id.get("demo-inbox-hiring")
    if hiring:
        start = windows["hiring_panel_start"]
        received = _received_at(reference, "Asia/Hong_Kong", days=1, hours=11)
        hiring["subject"] = f"Candidate panel interview request for {_date_text(start)} {_time_text(start)}"
        hiring["body"] = (
            "Hello Avery,\n\n"
            f"Could you join a panel interview for Samir on {_date_text(start)} at {_time_text(start)} {start.tzname()}? "
            "The hiring manager and design lead are already available.\n\n"
            "Thanks,\nPriya"
        )
        hiring["snippet"] = (
            f"Could you join a panel interview for Samir on {_date_text(start)} at {_time_text(start)} {start.tzname()}?"
        )
        hiring["received"] = received.isoformat()

    sent_status = by_id.get("demo-sent-status")
    if sent_status:
        sent_status["received"] = _received_at(reference, "Asia/Hong_Kong", days=1, hours=1).isoformat()

    draft_vendor = by_id.get("demo-draft-vendor")
    if draft_vendor:
        draft_vendor["received"] = _received_at(reference, "Asia/Hong_Kong", days=2, hours=6).isoformat()

    trash_promo = by_id.get("demo-trash-promo")
    if trash_promo:
        trash_promo["received"] = _received_at(reference, "Asia/Hong_Kong", days=3, hours=2).isoformat()

    return payload


def _build_demo_calendar_seed(template_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(template_payload or {}))
    payload.setdefault("events", [])

    reference = demo_reference_now()
    windows = _event_window(reference)
    by_id = {str(item.get("id") or ""): item for item in payload.get("events", [])}
    tz_name = "Asia/Hong_Kong"

    standup = by_id.get("demo-event-launch-standup")
    if standup:
        standup["start"] = {"dateTime": windows["launch_standup_start"].isoformat(), "timeZone": tz_name}
        standup["end"] = {"dateTime": windows["launch_standup_end"].isoformat(), "timeZone": tz_name}
        standup["updated"] = _received_at(reference, tz_name, hours=1).isoformat()

    conflict = by_id.get("demo-event-client-rehearsal-conflict")
    if conflict:
        conflict["start"] = {"dateTime": windows["conflict_start"].isoformat(), "timeZone": tz_name}
        conflict["end"] = {"dateTime": windows["conflict_end"].isoformat(), "timeZone": tz_name}
        conflict["updated"] = _received_at(reference, tz_name, hours=1).isoformat()

    offsite = by_id.get("demo-event-offsite-travel")
    if offsite:
        offsite_start = windows["offsite_start"]
        offsite_end = windows["offsite_end"]
        offsite["start"] = {"date": offsite_start.date().isoformat()}
        offsite["end"] = {"date": offsite_end.date().isoformat()}
        offsite["updated"] = _received_at(reference, tz_name, days=1, hours=7).isoformat()

    return payload


def _ensure_state(seed_path: Path, state_path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    state_payload = _read_json(state_path)
    if state_payload:
        return state_payload

    seed_payload = _read_json(seed_path)
    if seed_path == settings.DEMO_EMAIL_FIXTURE_PATH:
        payload = _build_demo_mailbox_seed(seed_payload or dict(fallback))
    elif seed_path == settings.DEMO_CALENDAR_FIXTURE_PATH:
        payload = _build_demo_calendar_seed(seed_payload or dict(fallback))
    else:
        payload = seed_payload or dict(fallback)
    _write_json(state_path, payload)
    return payload


def load_demo_mailbox_state() -> Dict[str, Any]:
    payload = _ensure_state(
        settings.DEMO_EMAIL_FIXTURE_PATH,
        settings.DEMO_EMAIL_STATE_PATH,
        {"user": dict(DEFAULT_DEMO_USER), "labels": [], "messages": []},
    )
    payload.setdefault("user", dict(DEFAULT_DEMO_USER))
    payload.setdefault("labels", [])
    payload.setdefault("messages", [])
    return payload


def save_demo_mailbox_state(payload: Dict[str, Any]) -> None:
    _write_json(settings.DEMO_EMAIL_STATE_PATH, payload)


def load_demo_calendar_state() -> Dict[str, Any]:
    payload = _ensure_state(
        settings.DEMO_CALENDAR_FIXTURE_PATH,
        settings.DEMO_CALENDAR_STATE_PATH,
        {"events": []},
    )
    payload.setdefault("events", [])
    return payload


def save_demo_calendar_state(payload: Dict[str, Any]) -> None:
    _write_json(settings.DEMO_CALENDAR_STATE_PATH, payload)


def demo_user_profile() -> Dict[str, Any]:
    user = dict(load_demo_mailbox_state().get("user") or {})
    merged = dict(DEFAULT_DEMO_USER)
    merged.update(user)
    merged["demo_mode"] = True
    return merged


def find_demo_message(*, scenario_id: str | None = None, demo_role: str | None = None) -> Dict[str, Any]:
    candidates = [
        load_demo_mailbox_state().get("messages") or [],
        (_build_demo_mailbox_seed(_read_json(settings.DEMO_EMAIL_FIXTURE_PATH)).get("messages") or []),
    ]
    for messages in candidates:
        for item in messages:
            if scenario_id and item.get("scenario_id") != scenario_id:
                continue
            if demo_role and item.get("demo_role") != demo_role:
                continue
            return dict(item)
    return {}


def find_demo_event(*, scenario_id: str | None = None, demo_role: str | None = None) -> Dict[str, Any]:
    candidates = [
        load_demo_calendar_state().get("events") or [],
        (_build_demo_calendar_seed(_read_json(settings.DEMO_CALENDAR_FIXTURE_PATH)).get("events") or []),
    ]
    for events in candidates:
        for item in events:
            if scenario_id and item.get("scenario_id") != scenario_id:
                continue
            if demo_role and item.get("demo_role") != demo_role:
                continue
            return dict(item)
    return {}


def get_demo_script(script_id: str) -> Dict[str, Any]:
    for item in OFFICIAL_DEMO_SCRIPTS:
        if item["script_id"] == script_id:
            return dict(item)
    return {}


def list_demo_scripts() -> List[Dict[str, Any]]:
    return [dict(item) for item in OFFICIAL_DEMO_SCRIPTS]


def reset_demo_world() -> None:
    mailbox_seed = _read_json(settings.DEMO_EMAIL_FIXTURE_PATH)
    calendar_seed = _read_json(settings.DEMO_CALENDAR_FIXTURE_PATH)
    _write_json(
        settings.DEMO_EMAIL_STATE_PATH,
        _build_demo_mailbox_seed(mailbox_seed or {"user": dict(DEFAULT_DEMO_USER), "labels": [], "messages": []}),
    )
    _write_json(
        settings.DEMO_CALENDAR_STATE_PATH,
        _build_demo_calendar_seed(calendar_seed or {"events": []}),
    )
