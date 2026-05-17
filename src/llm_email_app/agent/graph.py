from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Protocol
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from llm_email_app.agent.approvals import ApprovalStore, RunStore, ThreadStore, TimelineStore, WorkItemStore
from llm_email_app.agent.memory.store import MarkdownMemoryStore
from llm_email_app.agent.risk import normalize_risk_level, should_require_approval
from llm_email_app.agent.state import AgentDecision, AgentState, InvocationContext
from llm_email_app.agent.tools import build_tool_registry
from llm_email_app.agent.tools.base import AgentTool
from llm_email_app.config import settings
from llm_email_app.demo_data import find_demo_event, find_demo_message, get_demo_script, list_demo_scripts
from llm_email_app.llm.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

HK_TZ = timezone(timedelta(hours=8))
CONFIRM_WORDS = {"yes", "y", "confirm", "approved", "approve", "go ahead", "ok", "okay", "sure", "确认", "同意"}
REJECT_WORDS = {"no", "n", "reject", "cancel", "stop", "dismiss", "取消", "拒绝"}
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
CHINESE_NUMBER_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_excerpt(value: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _contains_cjk(value: str) -> bool:
    return bool(CJK_PATTERN.search(value or ""))


def _contains_any(value: str, keywords: Iterable[str]) -> bool:
    candidate = value or ""
    return any(keyword and keyword in candidate for keyword in keywords)


def _chat_response_text(english: str, chinese: str, user_request: str) -> str:
    return chinese if _contains_cjk(user_request) else english


def _strip_intent_tokens(query: str, tokens: Iterable[str]) -> str:
    cleaned = query or ""
    for token in tokens:
        if not token:
            continue
        if _contains_cjk(token):
            cleaned = cleaned.replace(token, " ")
        else:
            cleaned = re.sub(rf"\b{re.escape(token)}\b", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_number_token(token: str) -> Optional[int]:
    if not token:
        return None
    token = token.strip()
    if token.isdigit():
        return int(token)
    if token in CHINESE_NUMBER_MAP:
        return CHINESE_NUMBER_MAP[token]
    if token == "十":
        return 10
    if "十" in token:
        left, right = token.split("十", 1)
        tens = CHINESE_NUMBER_MAP.get(left, 1 if left == "" else None)
        ones = CHINESE_NUMBER_MAP.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    return None


def _extract_sender_email(sender: str) -> str:
    match = re.search(r"<([^>]+)>", sender or "")
    if match:
        return match.group(1).strip()
    sender = (sender or "").strip()
    if "@" in sender and " " not in sender:
        return sender
    return ""


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        if "T" not in candidate:
            candidate = f"{candidate}T00:00:00+08:00"
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=HK_TZ)
        return parsed
    except Exception:
        return None


def _parse_event_request(user_request: str, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    text = (user_request or "").strip()
    lowered = text.lower()
    if not text:
        return None

    now = now or datetime.now(HK_TZ)
    target_date: Optional[date] = None

    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_match:
        target_date = datetime.fromisoformat(iso_match.group(1)).date()
    elif "tomorrow" in lowered:
        target_date = (now + timedelta(days=1)).date()
    elif "today" in lowered:
        target_date = now.date()
    elif "明天" in text:
        target_date = (now + timedelta(days=1)).date()
    elif "今天" in text or "今日" in text:
        target_date = now.date()
    else:
        slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
        if slash_match:
            day, month = slash_match.groups()
            target_date = date(now.year, int(month), int(day))
        else:
            cjk_date_match = re.search(r"(?:(\d{1,2})月)?\s*(\d{1,2})[日号]", text)
            if cjk_date_match:
                month_value = int(cjk_date_match.group(1) or now.month)
                day_value = int(cjk_date_match.group(2))
                target_date = date(now.year, month_value, day_value)

    if target_date is None:
        return None

    hour = None
    minute = 0
    time_match = re.search(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lowered)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        marker = time_match.group(3)
        if marker == "pm" and hour < 12:
            hour += 12
        if marker == "am" and hour == 12:
            hour = 0
    else:
        time_match = re.search(r"(?:at\s+)?(\d{1,2}):(\d{2})\b", lowered)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        else:
            cjk_time_match = re.search(
                r"(上午|中午|下午|晚上|傍晚|早上|凌晨)?\s*([零〇一二两三四五六七八九十\d]{1,3})点(?:(半)|([零〇一二两三四五六七八九十\d]{1,3})分?)?",
                text,
            )
            if cjk_time_match:
                marker = cjk_time_match.group(1) or ""
                hour = _parse_number_token(cjk_time_match.group(2) or "")
                if cjk_time_match.group(3):
                    minute = 30
                else:
                    minute = _parse_number_token(cjk_time_match.group(4) or "") or 0
                if hour is not None:
                    if marker in {"下午", "晚上", "傍晚"} and hour < 12:
                        hour += 12
                    elif marker == "中午" and hour < 11:
                        hour += 12
                    elif marker == "凌晨" and hour == 12:
                        hour = 0

    if hour is None:
        return None

    duration = timedelta(hours=1)
    duration_match = re.search(r"\bfor\s+(\d{1,3})\s+(minute|minutes|hour|hours)\b", lowered)
    if duration_match:
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)
        duration = timedelta(minutes=amount) if "minute" in unit else timedelta(hours=amount)

    title = "Meeting"
    about_match = re.search(r"(?:about|for|called)\s+(.+)$", text, flags=re.IGNORECASE)
    if about_match:
        candidate = re.sub(r"\s+at\s+.+$", "", about_match.group(1), flags=re.IGNORECASE).strip(" .")
        if candidate:
            title = candidate[:80]
    else:
        cjk_about_match = re.search(r"关于(.+?)(?:的?(?:会议|日程|安排|活动|事件))?(?:$|，|。)", text)
        if cjk_about_match:
            candidate = cjk_about_match.group(1).strip(" ，。")
            if candidate:
                title = candidate[:80]

    start_dt = datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=HK_TZ)
    end_dt = start_dt + duration
    return {
        "title": "会议" if _contains_cjk(text) and title == "Meeting" else title,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "timeZone": "Asia/Hong_Kong",
        "notes": "",
        "attendees": [],
        "location": "",
    }


def _proposal_conflicts(proposal: Dict[str, Any], events: Iterable[Dict[str, Any]]) -> bool:
    start_dt = _parse_iso_datetime(proposal.get("start") or "")
    end_dt = _parse_iso_datetime(proposal.get("end") or "")
    if not start_dt or not end_dt:
        return False
    for event in events:
        event_start = _parse_iso_datetime((event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or "")
        event_end = _parse_iso_datetime((event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date") or "")
        if not event_start or not event_end:
            continue
        if event_start < end_dt and event_end > start_dt:
            return True
    return False


def _tool_history(state: AgentState) -> List[Dict[str, Any]]:
    return list(state.get("tool_history") or [])


def _last_tool_name(state: AgentState) -> Optional[str]:
    history = _tool_history(state)
    if not history:
        return None
    return history[-1].get("tool_name")


def _last_result_for_tool(state: AgentState, tool_name: str) -> Dict[str, Any]:
    for record in reversed(_tool_history(state)):
        if record.get("tool_name") == tool_name:
            return dict(record.get("result") or {})
    return {}


def _overlapping_event(proposal: Dict[str, Any], events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    start_dt = _parse_iso_datetime(proposal.get("start") or "")
    end_dt = _parse_iso_datetime(proposal.get("end") or "")
    if not start_dt or not end_dt:
        return {}
    for event in events:
        event_start = _parse_iso_datetime((event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or "")
        event_end = _parse_iso_datetime((event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date") or "")
        if not event_start or not event_end:
            continue
        if event_start < end_dt and event_end > start_dt:
            return dict(event)
    return {}


def _render_timeline_message(event_type: str, payload: Dict[str, Any]) -> str:
    if event_type == "task_understood":
        return payload.get("message") or "Task understood."
    if event_type == "next_action_selected":
        tool_name = payload.get("tool_name")
        if tool_name:
            return f"Selected next action: {tool_name}."
        return payload.get("message") or "Selected the next step."
    if event_type == "tool_started":
        return f"Running {payload.get('tool_name')}."
    if event_type == "tool_finished":
        return f"Finished {payload.get('tool_name')}."
    if event_type == "needs_input":
        return payload.get("message") or "Waiting for user input."
    if event_type == "resumed":
        return payload.get("message") or "Resumed after user input."
    if event_type == "completed":
        return payload.get("message") or "Completed."
    if event_type == "error":
        return payload.get("message") or "An error occurred."
    return payload.get("message") or event_type.replace("_", " ").capitalize()


def _official_script_final_status(state: AgentState) -> str:
    return "completed" if state.get("thread_kind") == "official" else "ready"


def _demo_draft_for_choice(email_payload: Dict[str, Any], choice: str, conflict_event: Dict[str, Any]) -> Dict[str, str]:
    subject = f"Re: {email_payload.get('subject') or 'meeting request'}".strip()
    sender_name = (email_payload.get("from") or "there").split("<", 1)[0].strip() or "there"
    conflict_title = conflict_event.get("summary") or "the existing event"
    if choice == "keep_existing":
        body = (
            f"Hi {sender_name},\n\n"
            "I already have a conflicting commitment at that time, so I can't confirm the rehearsal as requested. "
            "Could you suggest another slot later that day or early next week?\n\n"
            "Thanks,\nAvery"
        )
    elif choice == "accept_new":
        body = (
            f"Hi {sender_name},\n\n"
            "I can make the rehearsal time and I've cleared the conflicting calendar hold. "
            "Please keep me on the invite and send any prep notes you want covered beforehand.\n\n"
            "Thanks,\nAvery"
        )
    else:
        body = (
            f"Hi {sender_name},\n\n"
            "I noticed the proposed rehearsal overlaps with another commitment on my calendar "
            f"({conflict_title}). I'm holding off on changing anything until we confirm priority. "
            "If moving the rehearsal is easier, please send another option.\n\n"
            "Thanks,\nAvery"
        )
    return {"subject": subject, "body": body}


class DecisionOutput(BaseModel):
    action: str = Field(default="finish")
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    response_text: str = ""
    reason: str = ""
    confidence: float = 0.0


class DecisionEngine(Protocol):
    def decide(
        self,
        state: AgentState,
        context: InvocationContext,
        tools: Dict[str, AgentTool],
    ) -> AgentDecision:
        ...


class ScriptedDecisionEngine:
    def __init__(self, planner):
        self._planner = planner

    def decide(
        self,
        state: AgentState,
        context: InvocationContext,
        tools: Dict[str, AgentTool],
    ) -> AgentDecision:
        return dict(self._planner(state, context, tools))


class LangChainDecisionEngine:
    def __init__(self, model_name: str, api_key: str, api_base: Optional[str] = None) -> None:
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "temperature": 0,
        }
        if api_base:
            kwargs["base_url"] = api_base
        model = ChatOpenAI(**kwargs)
        self._structured = model.with_structured_output(DecisionOutput, strict=False)

    def decide(
        self,
        state: AgentState,
        context: InvocationContext,
        tools: Dict[str, AgentTool],
    ) -> AgentDecision:
        tool_catalog = "\n".join(
            f"- {name}: {tool.description} (risk={tool.risk_level})"
            for name, tool in sorted(tools.items())
        )
        prompt_state = {
            "agent_kind": state.get("agent_kind"),
            "mode": state.get("mode"),
            "shadow_mode": state.get("shadow_mode"),
            "email_id": state.get("email_id"),
            "email_metadata": state.get("email_metadata"),
            "user_request": state.get("user_request"),
            "summary": state.get("summary"),
            "memory_context": state.get("memory_context"),
            "rules": context.rules,
            "automation_settings": context.automation_settings,
            "last_tool_result": state.get("last_tool_result"),
            "tool_history": _tool_history(state)[-4:],
        }
        messages = [
            SystemMessage(
                content=(
                    "You are the control policy for an email and calendar assistant. "
                    "Choose the single best next action. Use exactly one tool at a time or finish. "
                    "If the task is complete or the next tool is unnecessary, finish."
                )
            ),
            HumanMessage(
                content=(
                    "Available tools:\n"
                    f"{tool_catalog}\n\n"
                    "Current state:\n"
                    f"{json.dumps(prompt_state, ensure_ascii=False, indent=2, default=str)}"
                )
            ),
        ]
        result = self._structured.invoke(messages)
        return result.dict() if hasattr(result, "dict") else dict(result)


class HeuristicDecisionEngine:
    def decide(
        self,
        state: AgentState,
        context: InvocationContext,
        tools: Dict[str, AgentTool],
    ) -> AgentDecision:
        if state.get("agent_kind") == "triage":
            return self._decide_triage(state, context)
        return self._decide_chat(state, context)

    def _decide_triage(self, state: AgentState, context: InvocationContext) -> AgentDecision:
        last_tool = _last_tool_name(state)
        summary_result = _last_result_for_tool(state, "summarize_email")
        label_result = _last_result_for_tool(state, "evaluate_label_rules")
        matched_rule_ids = [item.get("rule_id") for item in (label_result.get("matches") or []) if item.get("rule_id")]
        labels_applied = "apply_label" in list(state.get("completed_actions") or [])

        if not last_tool:
            if context.rules:
                return {
                    "action": "tool",
                    "tool_name": "evaluate_label_rules",
                    "tool_args": {"email_id": state.get("email_id")},
                    "response_text": "",
                    "reason": "Need to evaluate label rules before acting on the email.",
                    "confidence": 0.96,
                }
            return {
                "action": "tool",
                "tool_name": "summarize_email",
                "tool_args": {"email_id": state.get("email_id")},
                "response_text": "",
                "reason": "No rules configured, so summarize the email directly.",
                "confidence": 0.92,
            }

        if last_tool == "evaluate_label_rules":
            return {
                "action": "tool",
                "tool_name": "summarize_email",
                "tool_args": {"email_id": state.get("email_id")},
                "response_text": "",
                "reason": "Read-only understanding should happen before any write action.",
                "confidence": 0.9,
            }

        if last_tool == "apply_label":
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": summary_result.get("summary") or "Email triage completed.",
                "reason": "The remaining write action is done.",
                "confidence": 0.94,
            }

        if last_tool == "summarize_email":
            proposals = (state.get("last_tool_result") or {}).get("proposals") or []
            if not proposals:
                if matched_rule_ids and not labels_applied:
                    return {
                        "action": "tool",
                        "tool_name": "apply_label",
                        "tool_args": {
                            "message_id": state.get("email_id"),
                            "rule_ids": matched_rule_ids,
                        },
                        "response_text": "",
                        "reason": "Scheduling work is done, so apply the matched labels now.",
                        "confidence": 0.9,
                    }
                return {
                    "action": "finish",
                    "tool_name": None,
                    "tool_args": {},
                    "response_text": (state.get("last_tool_result") or {}).get("summary") or "No scheduling action was extracted from this email.",
                    "reason": "No calendar proposal was found.",
                    "confidence": 0.93,
                }
            proposal = dict(proposals[0])
            return {
                "action": "tool",
                "tool_name": "list_calendar_events",
                "tool_args": {
                    "time_min": proposal.get("start"),
                    "time_max": proposal.get("end"),
                    "max_results": 20,
                },
                "response_text": "",
                "reason": "Check for calendar conflicts before deciding whether to schedule or queue a proposal.",
                "confidence": 0.88,
            }

        if last_tool == "list_calendar_events":
            proposal = dict((summary_result.get("proposals") or [{}])[0] or {})
            if not proposal:
                return {
                    "action": "finish",
                    "tool_name": None,
                    "tool_args": {},
                    "response_text": "No valid calendar proposal remained after inspection.",
                    "reason": "The proposal was missing after calendar inspection.",
                    "confidence": 0.87,
                }
            events = (state.get("last_tool_result") or {}).get("events") or []
            if _proposal_conflicts(proposal, events):
                proposal["notes"] = ((proposal.get("notes") or "").strip() + "\n\nPotential calendar conflict detected.").strip()
                return {
                    "action": "tool",
                    "tool_name": "queue_event_proposal",
                    "tool_args": {
                        "proposal": proposal,
                        "email_id": state.get("email_id"),
                        "email_subject": (state.get("loaded_email") or {}).get("subject"),
                        "email_summary": summary_result.get("summary") or "",
                    },
                    "response_text": "",
                    "reason": "A possible conflict was found, so queue the event for human review.",
                    "confidence": 0.91,
                }
            if context.automation_settings.get("auto_add_events"):
                return {
                    "action": "tool",
                    "tool_name": "create_calendar_event",
                    "tool_args": {"proposal": proposal},
                    "response_text": "",
                    "reason": "No conflict was found and automatic event creation is enabled.",
                    "confidence": 0.86,
                }
            return {
                "action": "tool",
                "tool_name": "queue_event_proposal",
                "tool_args": {
                    "proposal": proposal,
                    "email_id": state.get("email_id"),
                    "email_subject": (state.get("loaded_email") or {}).get("subject"),
                    "email_summary": summary_result.get("summary") or "",
                },
                "response_text": "",
                "reason": "Automatic event creation is disabled, so queue a proposal.",
                "confidence": 0.9,
            }

        if last_tool in {"queue_event_proposal", "create_calendar_event"}:
            if matched_rule_ids and not labels_applied:
                return {
                    "action": "tool",
                    "tool_name": "apply_label",
                    "tool_args": {
                        "message_id": state.get("email_id"),
                        "rule_ids": matched_rule_ids,
                    },
                    "response_text": "",
                    "reason": "Follow through on the matched labels after handling schedule extraction.",
                    "confidence": 0.88,
                }
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": summary_result.get("summary") or "Email triage completed.",
                "reason": "All required email actions are complete.",
                "confidence": 0.95,
            }

        return {
            "action": "finish",
            "tool_name": None,
            "tool_args": {},
            "response_text": "Email triage finished with no further action.",
            "reason": "No additional heuristic step matched.",
            "confidence": 0.7,
        }

    def _decide_flagship_script(self, state: AgentState, context: InvocationContext) -> AgentDecision:
        email_payload = state.get("loaded_email") or find_demo_message(scenario_id="client_launch_conflict", demo_role="flagship")
        proposal = dict(email_payload.get("event_request") or {})
        last_tool = _last_tool_name(state)
        last_response = dict(state.get("last_user_response") or {})
        last_action = str(last_response.get("action") or "")
        response_payload = dict(last_response.get("payload") or {})
        choice = str(response_payload.get("choice") or state.get("demo_context", {}).get("conflict_choice") or "")
        latest_events = (state.get("last_tool_result") or {}).get("events") or []
        conflict_event = _overlapping_event(proposal, latest_events) or dict(state.get("demo_context", {}).get("conflict_event") or {})

        if not last_tool:
            return {
                "action": "tool",
                "tool_name": "read_email",
                "tool_args": {"email_id": state.get("email_id") or email_payload.get("id")},
                "response_text": "",
                "reason": "Read the anchored rehearsal email before taking action.",
                "confidence": 0.98,
            }

        if last_tool == "read_email":
            return {
                "action": "tool",
                "tool_name": "list_calendar_events",
                "tool_args": {
                    "time_min": proposal.get("start"),
                    "time_max": proposal.get("end"),
                    "max_results": 20,
                },
                "response_text": "",
                "reason": "Inspect the calendar to confirm whether the requested rehearsal conflicts with existing events.",
                "confidence": 0.97,
            }

        if last_tool == "list_calendar_events" and not choice:
            return {
                "action": "work_item",
                "work_item_type": "conflict_decision",
                "work_item_title": "Scheduling conflict needs your input",
                "work_item_question": "Which event should take priority?",
                "work_item_context": {
                    "scenario_id": "client_launch_conflict",
                    "new_request": proposal,
                    "current_event": conflict_event,
                    "agent_recommendation": {
                        "choice": "keep_existing",
                        "reason": "The existing exec briefing is already on the calendar and the email explicitly offers to move the rehearsal.",
                    },
                    "why_input_is_needed": "The assistant found a real calendar conflict and does not have authority to choose between the two commitments.",
                },
                "allowed_actions": ["choose"],
                "allowed_responses": ["keep_existing", "accept_new", "suggest_only"],
                "response_text": "",
                "reason": "A scheduling conflict requires explicit human judgment.",
                "confidence": 0.99,
                "stable_status": "needs_input",
            }

        if last_action == "choose":
            if choice == "accept_new" and last_tool != "delete_calendar_event":
                return {
                    "action": "tool",
                    "tool_name": "delete_calendar_event",
                    "tool_args": {"event_id": conflict_event.get("id")},
                    "response_text": "",
                    "reason": "The user prioritized the new rehearsal, so remove the conflicting event from the demo calendar.",
                    "confidence": 0.95,
                }
            draft = _demo_draft_for_choice(email_payload, choice or "suggest_only", conflict_event)
            to = _extract_sender_email(email_payload.get("from") or "")
            if context.mode == "auto":
                return {
                    "action": "tool",
                    "tool_name": "create_draft",
                    "tool_args": {
                        "to": to,
                        "subject": draft["subject"],
                        "body": draft["body"],
                        "reply_to_message_id": email_payload.get("id"),
                    },
                    "response_text": "",
                    "reason": "Auto mode continues directly to draft creation after the conflict decision.",
                    "confidence": 0.93,
                }
            return {
                "action": "work_item",
                "work_item_type": "draft_review",
                "work_item_title": "Review draft reply",
                "work_item_question": "Approve, reject, or edit the draft reply.",
                "work_item_context": {
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "to": to,
                    "reply_to_message_id": email_payload.get("id"),
                },
                "allowed_actions": ["approve", "reject", "edit"],
                "allowed_responses": [],
                "response_text": "",
                "reason": "Semi-auto mode requires review before saving the reply draft.",
                "confidence": 0.94,
                "stable_status": "needs_input",
            }

        if last_tool == "delete_calendar_event" and last_action not in {"approve", "reject", "edit"}:
            draft = _demo_draft_for_choice(email_payload, choice or "accept_new", conflict_event)
            return {
                "action": "work_item",
                "work_item_type": "draft_review",
                "work_item_title": "Review draft reply",
                "work_item_question": "Approve, reject, or edit the draft reply.",
                "work_item_context": {
                    "subject": draft["subject"],
                    "body": draft["body"],
                    "to": _extract_sender_email(email_payload.get("from") or ""),
                    "reply_to_message_id": email_payload.get("id"),
                },
                "allowed_actions": ["approve", "reject", "edit"],
                "allowed_responses": [],
                "response_text": "",
                "reason": "After updating the calendar, the next stable step is draft review.",
                "confidence": 0.95,
                "stable_status": "needs_input",
            }

        if last_tool == "create_draft":
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": "Resolved the conflict flow and saved the final reply draft.",
                "reason": "The flagship script reached its final stable state.",
                "confidence": 0.99,
            }

        if last_action in {"approve", "edit"}:
            draft_context = dict(last_response.get("context") or {})
            body = draft_context.get("body") or response_payload.get("body") or ""
            subject = draft_context.get("subject") or response_payload.get("subject") or ""
            if last_action == "edit":
                subject = response_payload.get("subject") or subject
                body = response_payload.get("body") or body
            return {
                "action": "tool",
                "tool_name": "create_draft",
                "tool_args": {
                    "to": draft_context.get("to") or _extract_sender_email(email_payload.get("from") or ""),
                    "subject": subject,
                    "body": body,
                    "reply_to_message_id": draft_context.get("reply_to_message_id") or email_payload.get("id"),
                },
                "response_text": "",
                "reason": "Persist the reviewed draft to Gmail drafts.",
                "confidence": 0.96,
            }

        if last_action == "reject":
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": "Stopped after draft review was rejected. No draft was saved.",
                "reason": "The user rejected the draft, so the official script ends without saving it.",
                "confidence": 0.98,
            }

        return {
            "action": "finish",
            "tool_name": None,
            "tool_args": {},
            "response_text": "The flagship demo reached a stable state.",
            "reason": "No additional flagship step matched.",
            "confidence": 0.8,
        }

    def _decide_schedule_script(self, state: AgentState, context: InvocationContext) -> AgentDecision:
        last_tool = _last_tool_name(state)
        if not last_tool:
            return {
                "action": "tool",
                "tool_name": "list_calendar_events",
                "tool_args": {"days_ahead": 7, "max_results": 20},
                "response_text": "",
                "reason": "Show the next week of calendar events.",
                "confidence": 0.97,
            }
        if last_tool == "list_calendar_events":
            count = int((state.get("last_tool_result") or {}).get("count") or 0)
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": f"Reviewed your next 7 days and found {count} calendar events.",
                "reason": "The schedule overview script is complete.",
                "confidence": 0.96,
            }
        return {
            "action": "finish",
            "tool_name": None,
            "tool_args": {},
            "response_text": "Completed the schedule overview script.",
            "reason": "No additional schedule step matched.",
            "confidence": 0.8,
        }

    def _decide_search_script(self, state: AgentState, context: InvocationContext) -> AgentDecision:
        last_tool = _last_tool_name(state)
        last_result = state.get("last_tool_result") or {}
        anchored_email = state.get("loaded_email") or find_demo_message(scenario_id="budget_summary")
        if not last_tool:
            return {
                "action": "tool",
                "tool_name": "search_emails",
                "tool_args": {"query": "budget", "limit": 5},
                "response_text": "",
                "reason": "Search for the anchored budget email before summarizing it.",
                "confidence": 0.97,
            }
        if last_tool == "search_emails":
            emails = last_result.get("emails") or []
            target = emails[0] if emails else {}
            return {
                "action": "tool",
                "tool_name": "read_email",
                "tool_args": {"email_id": target.get("id")},
                "response_text": "",
                "reason": "Read the most relevant budget email before summarizing it.",
                "confidence": 0.95,
            }
        if last_tool == "read_email":
            return {
                "action": "tool",
                "tool_name": "summarize_email",
                "tool_args": {"email_id": (state.get("last_tool_result") or {}).get("id") or state.get("email_id") or anchored_email.get("id")},
                "response_text": "",
                "reason": "Summarize the anchored budget email.",
                "confidence": 0.95,
            }
        if last_tool == "summarize_email":
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": last_result.get("summary") or "Summarized the most relevant budget email.",
                "reason": "The search-and-summarize script is complete.",
                "confidence": 0.97,
            }
        return {
            "action": "finish",
            "tool_name": None,
            "tool_args": {},
            "response_text": "Completed the search-and-summarize script.",
            "reason": "No additional search script step matched.",
            "confidence": 0.8,
        }

    def _decide_chat(self, state: AgentState, context: InvocationContext) -> AgentDecision:
        script_id = state.get("script_id") or context.script_id
        if script_id == "flagship_conflict":
            return self._decide_flagship_script(state, context)
        if script_id == "show_schedule":
            return self._decide_schedule_script(state, context)
        if script_id == "search_and_summarize":
            return self._decide_search_script(state, context)

        request = (state.get("user_request") or "").strip()
        lowered = request.lower()
        last_tool = _last_tool_name(state)
        last_result = state.get("last_tool_result") or {}

        if not last_tool:
            calendar_show_words = {"show", "list", "see", "check", "upcoming", "what's on", "查看", "看看", "显示", "列出", "接下来", "最近"}
            calendar_nouns = {"calendar", "schedule", "events", "event", "日历", "日程", "安排", "会议"}
            if _contains_any(lowered, calendar_show_words) and _contains_any(lowered, calendar_nouns):
                return {
                    "action": "tool",
                    "tool_name": "list_calendar_events",
                    "tool_args": {"days_ahead": 7, "max_results": 20},
                    "response_text": "",
                    "reason": "The user asked to inspect the calendar.",
                    "confidence": 0.9,
                }

            email_search_words = {"search", "find", "look for", "查找", "搜索", "找", "查"}
            email_nouns = {"email", "emails", "mail", "邮件", "邮箱"}
            if _contains_any(lowered, email_search_words) and _contains_any(lowered, email_nouns):
                query = _strip_intent_tokens(
                    request,
                    ("search", "find", "look for", "emails", "email", "mail", "about", "查找", "搜索", "邮件", "邮箱", "帮我", "相关", "的"),
                )
                return {
                    "action": "tool",
                    "tool_name": "search_emails",
                    "tool_args": {"query": _message_excerpt(query, 80) or "meeting", "limit": 10},
                    "response_text": "",
                    "reason": "Search the inbox for matching emails.",
                    "confidence": 0.9,
                }

            if _contains_any(lowered, {"recent emails", "latest emails", "inbox", "recent messages", "最近邮件", "最新邮件", "收件箱", "最近的邮件"}):
                return {
                    "action": "tool",
                    "tool_name": "list_recent_emails",
                    "tool_args": {"limit": 10, "folder": "inbox"},
                    "response_text": "",
                    "reason": "List recent inbox emails.",
                    "confidence": 0.93,
                }

            if _contains_any(lowered, {"summarize", "summary", "reply", "draft", "read", "总结", "概括", "回复", "草稿", "阅读", "查看"}) and _contains_any(lowered, {"email", "mail", "message", "邮件", "邮箱", "消息"}):
                if _contains_any(lowered, {"latest", "recent", "最新", "最近"}):
                    return {
                        "action": "tool",
                        "tool_name": "list_recent_emails",
                        "tool_args": {"limit": 5, "folder": "inbox"},
                        "response_text": "",
                        "reason": "Need to resolve which recent email the user means.",
                        "confidence": 0.85,
                    }
                return {
                    "action": "tool",
                    "tool_name": "search_emails",
                    "tool_args": {"query": _message_excerpt(request, 80), "limit": 5},
                    "response_text": "",
                    "reason": "Resolve the target email before reading or drafting.",
                    "confidence": 0.83,
                }

            schedule_create_words = {"schedule", "book", "add event", "create event", "安排", "添加", "新建", "创建", "预定"}
            if _contains_any(lowered, schedule_create_words) and not _contains_any(lowered, {"email", "mail", "邮件", "邮箱"}):
                proposal = _parse_event_request(request)
                if not proposal:
                    return {
                        "action": "finish",
                        "tool_name": None,
                        "tool_args": {},
                        "response_text": _chat_response_text(
                            "I need a date and start time before I can schedule that event.",
                            "我要先知道日期和开始时间，才能帮你安排这个日程。",
                            request,
                        ),
                        "reason": "The scheduling request did not contain enough time information.",
                        "confidence": 0.95,
                    }
                return {
                    "action": "tool",
                    "tool_name": "list_calendar_events",
                    "tool_args": {
                        "time_min": proposal.get("start"),
                        "time_max": proposal.get("end"),
                        "max_results": 20,
                    },
                    "response_text": "",
                    "reason": "Inspect the calendar before creating the requested event.",
                    "confidence": 0.9,
                }

            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": _chat_response_text(
                    "I can search emails, read and summarize them, draft replies, inspect your calendar, and schedule events.",
                    "我可以搜索邮件、读取和总结邮件、起草回复、查看日历，以及安排日程。",
                    request,
                ),
                "reason": "The request did not map to a specific tool flow.",
                "confidence": 0.7,
            }

        if last_tool == "list_calendar_events":
            proposal = _parse_event_request(request)
            if proposal:
                if _proposal_conflicts(proposal, last_result.get("events") or []):
                    return {
                        "action": "finish",
                        "tool_name": None,
                        "tool_args": {},
                        "response_text": _chat_response_text(
                            "I found a calendar conflict in that time window, so I did not create the event.",
                            "这个时间段里有日历冲突，所以我没有创建这个日程。",
                            request,
                        ),
                        "reason": "Conflict detection blocked automatic event creation.",
                        "confidence": 0.93,
                    }
                return {
                    "action": "tool",
                    "tool_name": "create_calendar_event",
                    "tool_args": {"proposal": proposal},
                    "response_text": "",
                    "reason": "The requested time is clear, so create the event.",
                    "confidence": 0.88,
                }
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": _chat_response_text(
                    f"I found {last_result.get('count', 0)} calendar events in that range.",
                    f"我找到了 {last_result.get('count', 0)} 个相关日程。",
                    request,
                ),
                "reason": "The calendar inspection itself answers the request.",
                "confidence": 0.9,
            }

        if last_tool in {"search_emails", "list_recent_emails"}:
            emails = last_result.get("emails") or []
            if not emails:
                return {
                    "action": "finish",
                    "tool_name": None,
                    "tool_args": {},
                    "response_text": _chat_response_text(
                        "I did not find any matching emails.",
                        "我没有找到匹配的邮件。",
                        request,
                    ),
                    "reason": "There are no matching email results to inspect further.",
                    "confidence": 0.95,
                }
            target = emails[0]
            if any(word in lowered for word in {"summarize", "summary", "reply", "draft", "read", "open"}):
                return {
                    "action": "tool",
                    "tool_name": "read_email",
                    "tool_args": {"email_id": target.get("id")},
                    "response_text": "",
                    "reason": "Read the most relevant email before the next step.",
                    "confidence": 0.88,
                }
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": last_result.get("message") or _chat_response_text(
                    f"Found {len(emails)} matching emails.",
                    f"我找到了 {len(emails)} 封匹配的邮件。",
                    request,
                ),
                "reason": "The search result itself answers the request.",
                "confidence": 0.9,
            }

        if last_tool == "read_email":
            if any(word in lowered for word in {"summarize", "summary", "reply", "draft"}):
                return {
                    "action": "tool",
                    "tool_name": "summarize_email",
                    "tool_args": {"email_id": last_result.get("id") or state.get("email_id")},
                    "response_text": "",
                    "reason": "Summarize the email before drafting or reporting back.",
                    "confidence": 0.87,
                }
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": _message_excerpt(last_result.get("body") or last_result.get("snippet") or "", 320) or _chat_response_text(
                    "I opened the email.",
                    "我已经打开这封邮件。",
                    request,
                ),
                "reason": "The email has already been read and displayed.",
                "confidence": 0.85,
            }

        if last_tool == "summarize_email":
            if any(word in lowered for word in {"reply", "draft"}):
                draft_reply = last_result.get("draft_reply")
                email_payload = state.get("loaded_email") or {}
                to = _extract_sender_email(email_payload.get("from") or "")
                if not draft_reply or not to:
                    return {
                        "action": "finish",
                        "tool_name": None,
                        "tool_args": {},
                        "response_text": _chat_response_text(
                            "I could summarize the email, but I could not assemble a reply draft from it.",
                            "我已经总结了这封邮件，但还没法直接生成可用的回复草稿。",
                            request,
                        ),
                        "reason": "Draft creation requires sender and draft content.",
                        "confidence": 0.8,
                    }
                return {
                    "action": "tool",
                    "tool_name": "create_draft",
                    "tool_args": {
                        "to": to,
                        "subject": draft_reply.get("subject") or f"Re: {email_payload.get('subject') or ''}".strip(),
                        "body": draft_reply.get("body") or "",
                        "reply_to_message_id": email_payload.get("id") or state.get("email_id"),
                    },
                    "response_text": "",
                    "reason": "The LLM produced a draft reply, so save it to Gmail drafts.",
                    "confidence": 0.82,
                }
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": last_result.get("summary") or _chat_response_text(
                    "I summarized the email.",
                    "我已经总结了这封邮件。",
                    request,
                ),
                "reason": "The summary answers the user's request.",
                "confidence": 0.93,
            }

        if last_tool in {"create_draft", "create_calendar_event"}:
            return {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": "Done.",
                "reason": "The requested write action has completed.",
                "confidence": 0.95,
            }

        return {
            "action": "finish",
            "tool_name": None,
            "tool_args": {},
            "response_text": "I completed the current tool step.",
            "reason": "No further heuristic step matched.",
            "confidence": 0.7,
        }


@dataclass
class InvokeResult:
    payload: Dict[str, Any]
    interrupted: bool = False


class AgentRuntime:
    def __init__(
        self,
        checkpoint_path: Optional[Path] = None,
        approvals_path: Optional[Path] = None,
        work_items_path: Optional[Path] = None,
        threads_path: Optional[Path] = None,
        timeline_path: Optional[Path] = None,
        runs_path: Optional[Path] = None,
        memory_dir: Optional[Path] = None,
        llm_client: Optional[OpenAIClient] = None,
        decision_engine: Optional[DecisionEngine] = None,
        max_steps: Optional[int] = None,
        min_confidence: Optional[float] = None,
        auto_write_risk_limit: Optional[str] = None,
    ) -> None:
        self.max_steps = max_steps or settings.AGENT_MAX_STEPS
        self.min_confidence = min_confidence if min_confidence is not None else settings.AGENT_MIN_CONFIDENCE
        self.auto_write_risk_limit = normalize_risk_level(auto_write_risk_limit or settings.AGENT_AUTO_WRITE_RISK_LIMIT)
        self.llm_client = llm_client or OpenAIClient()
        self._heuristic_engine = HeuristicDecisionEngine()
        work_items_storage = work_items_path or settings.AGENT_WORK_ITEMS_PATH
        self.work_item_store = WorkItemStore(work_items_storage)
        self.approval_store = ApprovalStore(approvals_path or work_items_storage)
        self.thread_store = ThreadStore(threads_path or settings.AGENT_THREADS_PATH)
        self.timeline_store = TimelineStore(timeline_path or settings.AGENT_TIMELINE_PATH)
        self.run_store = RunStore(runs_path or settings.AGENT_RUNS_PATH)
        self.memory_store = MarkdownMemoryStore(memory_dir or settings.AGENT_MEMORY_DIR)
        self.tool_registry = build_tool_registry(self.memory_store)
        self._active_contexts: Dict[str, InvocationContext] = {}
        checkpoint_target = Path(checkpoint_path or settings.AGENT_CHECKPOINTS_PATH)
        checkpoint_target.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(
            str(checkpoint_target),
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(self._sqlite_conn)
        self.decision_engine = decision_engine or self._default_decision_engine()
        self.graph = self._build_graph()
        self._ensure_baseline_threads()

    def _default_decision_engine(self) -> DecisionEngine:
        if not isinstance(self.llm_client, OpenAIClient):
            return self._heuristic_engine

        model_name = ((getattr(self.llm_client, "model", None) or os.getenv("OPENAI_MODEL")) or "").strip()
        api_key = ((getattr(self.llm_client, "api_key", None) or settings.OPENAI_API_KEY) or "").strip()
        api_base = (
            (getattr(self.llm_client, "api_base", None) or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_API_URL"))
            or ""
        ).strip() or None
        if api_key and model_name:
            try:
                return LangChainDecisionEngine(model_name=model_name, api_key=api_key, api_base=api_base)
            except Exception as exc:
                logger.warning("LangChain decision engine unavailable, falling back to heuristics: %s", exc)
        return self._heuristic_engine

    def close(self) -> None:
        self._sqlite_conn.close()

    def reset_stores(self) -> None:
        self.work_item_store.clear()
        self.approval_store._store.clear()
        self.thread_store.clear()
        self.timeline_store.clear()
        self.run_store.clear()
        self._ensure_baseline_threads()

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "dry_run_supported": tool.dry_run_supported,
            }
            for name, tool in sorted(self.tool_registry.items())
        ]

    def list_approvals(self, status: Optional[str] = None, thread_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.approval_store.list(status=status, thread_id=thread_id, limit=limit)

    def list_work_items(self, status: Optional[str] = None, thread_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.work_item_store.list(status=status, thread_id=thread_id, limit=limit)

    def list_runs(self, thread_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        return self.run_store.list(thread_id=thread_id, limit=limit)

    def list_threads(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.thread_store.list(limit=limit)

    def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        return self.thread_store.get(thread_id)

    def get_timeline(self, thread_id: str) -> List[Dict[str, Any]]:
        return self.timeline_store.list(thread_id)

    def get_work_item(self, work_item_id: str) -> Optional[Dict[str, Any]]:
        return self.work_item_store.get(work_item_id)

    def continue_from_thread(self, source_thread_id: str) -> Dict[str, Any]:
        source_thread = self.thread_store.get(source_thread_id)
        if not source_thread:
            raise KeyError(f"Thread {source_thread_id} not found")
        source_state = self.graph.get_state(self._config(source_thread_id)).values or {}
        new_thread_id = f"chat-branch-{uuid.uuid4().hex[:8]}"
        branched = self.thread_store.create_or_replace(
            {
                "thread_id": new_thread_id,
                "thread_kind": "free",
                "script_id": None,
                "title": f"Continue from {source_thread.get('title') or source_thread_id}",
                "thread_title": source_thread.get("thread_title") or source_thread.get("title"),
                "status": "ready",
                "messages": list(source_thread.get("messages") or []),
                "branch_source_thread_id": source_thread_id,
                "seed_state": {
                    "summary": source_state.get("summary") or (source_thread.get("final_outcome") or {}).get("message") or "",
                    "demo_context": dict(source_state.get("demo_context") or {}),
                    "email_id": source_state.get("email_id"),
                    "email_metadata": dict(source_state.get("email_metadata") or {}),
                    "loaded_email": dict(source_state.get("loaded_email") or {}),
                },
            }
        )
        self.timeline_store.replace(new_thread_id, list(self.timeline_store.list(source_thread_id)))
        return branched

    def start_demo(
        self,
        *,
        script_id: str,
        user_id: str,
        gmail_client: Any = None,
        gcal_client: Any = None,
        mode: str = "semi_auto",
        shadow_mode: bool = False,
        log_callback=None,
    ) -> Dict[str, Any]:
        script = get_demo_script(script_id)
        if not script:
            raise KeyError(f"Unknown demo script: {script_id}")
        thread_id = script["thread_id"]
        context = InvocationContext(
            thread_id=thread_id,
            user_id=user_id,
            thread_kind="official",
            script_id=script_id,
            thread_title=script.get("thread_title"),
            agent_kind="chat",
            mode=mode,  # type: ignore[arg-type]
            shadow_mode=shadow_mode,
            source="demo",
            gmail_client=gmail_client,
            gcal_client=gcal_client,
            llm_client=self.llm_client,
            rules=[],
            automation_settings={"agent_mode": mode},
            log_callback=log_callback,
        )
        return self.run_chat(
            message=script["starter_message"],
            thread_id=thread_id,
            user_id=user_id,
            gmail_client=gmail_client,
            gcal_client=gcal_client,
            rules=[],
            automation_settings={"agent_mode": mode},
            mode=mode,
            shadow_mode=shadow_mode,
            source="demo",
            log_callback=log_callback,
            thread_kind="official",
            script_id=script_id,
            thread_title=script.get("thread_title"),
        )

    def _ensure_baseline_threads(self) -> None:
        for script in list_demo_scripts():
            self.thread_store.create_or_replace(
                {
                    "thread_id": script["thread_id"],
                    "thread_kind": script.get("thread_kind", "official"),
                    "script_id": script["script_id"],
                    "title": script["title"],
                    "thread_title": script.get("thread_title"),
                    "status": "ready",
                    "messages": [],
                    "demo_role": script.get("demo_role"),
                    "scenario_id": script.get("scenario_id"),
                    "starter_message": script.get("starter_message"),
                }
            )
        if not self.thread_store.get("chat-free-exploration"):
            self.thread_store.create_or_replace(
                {
                    "thread_id": "chat-free-exploration",
                    "thread_kind": "free",
                    "script_id": None,
                    "title": "Free exploration",
                    "thread_title": "Free exploration",
                    "status": "ready",
                    "messages": [],
                }
            )

    def run_chat(
        self,
        *,
        message: str,
        thread_id: str,
        user_id: str,
        gmail_client: Any = None,
        gcal_client: Any = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        automation_settings: Optional[Dict[str, Any]] = None,
        mode: str = "semi_auto",
        shadow_mode: bool = False,
        source: str = "chat",
        log_callback=None,
        proposal_writer=None,
        proposal_status_updater=None,
        thread_kind: str = "free",
        script_id: Optional[str] = None,
        thread_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        context = InvocationContext(
            thread_id=thread_id,
            user_id=user_id,
            thread_kind=thread_kind,  # type: ignore[arg-type]
            script_id=script_id,
            thread_title=thread_title,
            agent_kind="chat",
            mode=mode,  # type: ignore[arg-type]
            shadow_mode=shadow_mode,
            source=source,
            gmail_client=gmail_client,
            gcal_client=gcal_client,
            llm_client=self.llm_client,
            rules=rules or [],
            automation_settings=automation_settings or {},
            log_callback=log_callback,
            proposal_writer=proposal_writer,
            proposal_status_updater=proposal_status_updater,
        )
        existing_thread = self.thread_store.get(thread_id) or {}
        seed_state = dict(existing_thread.get("seed_state") or {})
        self.thread_store.create_or_replace(
            {
                **existing_thread,
                "thread_id": thread_id,
                "thread_kind": thread_kind,
                "script_id": script_id,
                "title": existing_thread.get("title") or thread_title or ("Chat thread" if thread_kind == "free" else "Official demo"),
                "thread_title": thread_title or existing_thread.get("thread_title"),
                "status": "in_progress",
                "messages": list(existing_thread.get("messages") or []),
            }
        )
        self.thread_store.append_message(
            thread_id,
            {"role": "user", "content": message, "timestamp": _utc_now()},
        )
        self._append_timeline(thread_id, "task_understood", {"message": _message_excerpt(message, 180)})
        config = self._config(thread_id)
        snapshot = self.graph.get_state(config)
        if snapshot.interrupts:
            work_item = next(iter(self.work_item_store.list(status="pending", thread_id=thread_id, limit=1)), None)
            normalized = (message or "").strip().lower()
            if work_item and normalized in CONFIRM_WORDS and "approve" in (work_item.get("allowed_actions") or []):
                return self.resume_work_item(
                    work_item_id=work_item["id"],
                    action="approve",
                    context=context,
                )
            if work_item and normalized in REJECT_WORDS and "reject" in (work_item.get("allowed_actions") or []):
                return self.resume_work_item(
                    work_item_id=work_item["id"],
                    action="reject",
                    context=context,
                )
            interrupt_payload = snapshot.interrupts[0].value if snapshot.interrupts else {}
            return self._format_interrupt_payload(thread_id, interrupt_payload)

        prior_values = snapshot.values or {}
        history = list(prior_values.get("recent_messages") or [])
        history.append({"role": "user", "content": message})
        initial_state: AgentState = {
            "thread_id": thread_id,
            "thread_kind": thread_kind,  # type: ignore[assignment]
            "thread_title": thread_title or existing_thread.get("thread_title") or existing_thread.get("title") or "",
            "script_id": script_id,
            "agent_kind": "chat",
            "user_id": user_id,
            "mode": mode,  # type: ignore[assignment]
            "shadow_mode": shadow_mode,
            "user_request": message,
            "recent_messages": history[-12:],
            "summary": prior_values.get("summary") or seed_state.get("summary") or "",
            "memory_context": {},
            "demo_context": {**dict(seed_state.get("demo_context") or {}), **dict(prior_values.get("demo_context") or {})},
            "rules": rules or [],
            "automation_settings": automation_settings or {},
            "current_step": 0,
            "max_steps": self.max_steps,
            "pending_decision": {},
            "pending_work_item_id": None,
            "last_user_response": {},
            "last_tool_result": {},
            "tool_history": [],
            "completed_actions": [],
            "memory_candidates": [],
            "final_outcome": {},
            "errors": [],
            "approvals": [],
        }
        if seed_state.get("email_id"):
            initial_state["email_id"] = seed_state.get("email_id")
            initial_state["email_metadata"] = dict(seed_state.get("email_metadata") or {})
            if seed_state.get("loaded_email"):
                initial_state["loaded_email"] = dict(seed_state.get("loaded_email") or {})
        if script_id == "flagship_conflict":
            anchored_email = find_demo_message(scenario_id="client_launch_conflict", demo_role="flagship")
            initial_state["email_id"] = anchored_email.get("id")
            initial_state["email_metadata"] = anchored_email
        elif script_id == "search_and_summarize":
            anchored_email = find_demo_message(scenario_id="budget_summary")
            if anchored_email:
                initial_state["email_id"] = anchored_email.get("id")
                initial_state["email_metadata"] = anchored_email
        return self._invoke(initial_state, context).payload

    def run_email_triage(
        self,
        *,
        email_id: str,
        user_id: str,
        gmail_client: Any = None,
        gcal_client: Any = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        automation_settings: Optional[Dict[str, Any]] = None,
        mode: str = "semi_auto",
        shadow_mode: bool = False,
        source: str = "automation",
        log_callback=None,
        proposal_writer=None,
        proposal_status_updater=None,
        email_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        thread_id = f"triage:{email_id}:{uuid.uuid4().hex[:8]}"
        context = InvocationContext(
            thread_id=thread_id,
            user_id=user_id,
            thread_kind="free",
            agent_kind="triage",
            mode=mode,  # type: ignore[arg-type]
            shadow_mode=shadow_mode,
            source=source,
            gmail_client=gmail_client,
            gcal_client=gcal_client,
            llm_client=self.llm_client,
            rules=rules or [],
            automation_settings=automation_settings or {},
            log_callback=log_callback,
            proposal_writer=proposal_writer,
            proposal_status_updater=proposal_status_updater,
        )
        initial_state: AgentState = {
            "thread_id": thread_id,
            "thread_kind": "free",
            "thread_title": f"Triage for {email_id}",
            "script_id": None,
            "agent_kind": "triage",
            "user_id": user_id,
            "mode": mode,  # type: ignore[assignment]
            "shadow_mode": shadow_mode,
            "email_id": email_id,
            "email_metadata": email_metadata or {},
            "recent_messages": [],
            "summary": "",
            "memory_context": {},
            "demo_context": {},
            "rules": rules or [],
            "automation_settings": automation_settings or {},
            "current_step": 0,
            "max_steps": self.max_steps,
            "pending_decision": {},
            "pending_work_item_id": None,
            "last_user_response": {},
            "last_tool_result": {},
            "tool_history": [],
            "completed_actions": [],
            "memory_candidates": [],
            "final_outcome": {},
            "errors": [],
            "approvals": [],
        }
        return self._invoke(initial_state, context).payload

    def resume_approval(
        self,
        *,
        approval_id: str,
        action: str,
        context: InvocationContext,
        tool_args: Optional[Dict[str, Any]] = None,
        response: Optional[str] = None,
    ) -> Dict[str, Any]:
        approval = self.approval_store.get(approval_id)
        if not approval:
            raise KeyError(f"Approval {approval_id} not found")
        thread_id = approval["thread_id"]
        context.thread_id = thread_id
        resume_payload = {"decision": action}
        if tool_args is not None:
            resume_payload["tool_args"] = tool_args
        if response is not None:
            resume_payload["response"] = response
        invoke_result = self._invoke(Command(resume=resume_payload), context, thread_id=thread_id)
        payload = dict(invoke_result.payload)
        payload["approval_id"] = approval_id
        return payload

    def resume_work_item(
        self,
        *,
        work_item_id: str,
        action: str,
        context: InvocationContext,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        work_item = self.work_item_store.get(work_item_id)
        if not work_item:
            raise KeyError(f"Work item {work_item_id} not found")
        if work_item.get("status") != "pending":
            raise ValueError(f"Work item {work_item_id} is not pending")
        allowed_actions = list(work_item.get("allowed_actions") or [])
        if action not in allowed_actions:
            raise ValueError(f"Action {action} is not allowed for work item {work_item_id}")
        thread_id = work_item["thread_id"]
        context.thread_id = thread_id
        resume_payload = {
            "work_item_id": work_item_id,
            "action": action,
            "payload": payload or {},
            "context": work_item.get("context") or {},
        }
        self._append_timeline(thread_id, "resumed", {"message": f"Resumed after responding to {work_item.get('type')}."})
        invoke_result = self._invoke(Command(resume=resume_payload), context, thread_id=thread_id)
        result = dict(invoke_result.payload)
        result.setdefault("work_item_id", work_item_id)
        result["responded_work_item_id"] = work_item_id
        return result

    def _invoke(
        self,
        input_payload: Any,
        context: InvocationContext,
        *,
        thread_id: Optional[str] = None,
    ) -> InvokeResult:
        active_thread_id = thread_id or context.thread_id
        self._active_contexts[active_thread_id] = context
        config = self._config(active_thread_id)
        try:
            result = self.graph.invoke(input_payload, config=config)
            if "__interrupt__" in result:
                interrupt_payload = result["__interrupt__"][0].value if result["__interrupt__"] else {}
                formatted = self._format_interrupt_payload(active_thread_id, interrupt_payload)
                self.thread_store.update(
                    active_thread_id,
                    status="needs_input",
                    active_work_item_id=formatted.get("work_item_id"),
                )
                if formatted.get("message"):
                    self.thread_store.append_message(
                        active_thread_id,
                        {"role": "assistant", "content": formatted["message"], "timestamp": _utc_now()},
                    )
                return InvokeResult(payload=formatted, interrupted=True)
            final_state = self.graph.get_state(config).values or result
            outcome = dict(final_state.get("final_outcome") or {})
            outcome.setdefault("thread_id", active_thread_id)
            thread_status = _official_script_final_status(final_state)
            self.thread_store.update(
                active_thread_id,
                status=thread_status,
                active_work_item_id=None,
                final_outcome=outcome,
                summary=final_state.get("summary") or "",
            )
            if outcome.get("message"):
                self.thread_store.append_message(
                    active_thread_id,
                    {"role": "assistant", "content": outcome["message"], "timestamp": _utc_now()},
                )
            return InvokeResult(payload=outcome, interrupted=False)
        finally:
            self._active_contexts.pop(active_thread_id, None)

    def _context_for(self, state: AgentState) -> InvocationContext:
        thread_id = state.get("thread_id") or ""
        context = self._active_contexts.get(thread_id)
        if context is None:
            raise RuntimeError(f"Missing invocation context for thread {thread_id}")
        return context

    def _config(self, thread_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _append_timeline(self, thread_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(payload)
        enriched.setdefault("message", _render_timeline_message(event_type, payload))
        return self.timeline_store.append(
            thread_id,
            {
                "type": event_type,
                "message": enriched["message"],
                "payload": payload,
            },
        )

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("load_email_context", self._load_email_context)
        builder.add_node("load_policies_and_memory", self._load_policies_and_memory)
        builder.add_node("agent_decide", self._agent_decide)
        builder.add_node("handle_work_item", self._handle_work_item)
        builder.add_node("risk_gate", self._risk_gate)
        builder.add_node("execute_tool", self._execute_tool)
        builder.add_node("reflect_on_result", self._reflect_on_result)
        builder.add_node("write_memory_candidates", self._write_memory_candidates)
        builder.add_node("finalize", self._finalize)

        builder.add_edge(START, "load_email_context")
        builder.add_edge("load_email_context", "load_policies_and_memory")
        builder.add_edge("load_policies_and_memory", "agent_decide")
        builder.add_conditional_edges(
            "agent_decide",
            self._route_after_decide,
            {
                "handle_work_item": "handle_work_item",
                "risk_gate": "risk_gate",
                "write_memory_candidates": "write_memory_candidates",
            },
        )
        builder.add_edge("handle_work_item", "agent_decide")
        builder.add_conditional_edges(
            "risk_gate",
            self._route_after_risk_gate,
            {
                "execute_tool": "execute_tool",
                "write_memory_candidates": "write_memory_candidates",
            },
        )
        builder.add_edge("execute_tool", "reflect_on_result")
        builder.add_conditional_edges(
            "reflect_on_result",
            self._route_after_reflection,
            {
                "agent_decide": "agent_decide",
                "write_memory_candidates": "write_memory_candidates",
            },
        )
        builder.add_edge("write_memory_candidates", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile(checkpointer=self._checkpointer)

    def _load_email_context(self, state: AgentState) -> Dict[str, Any]:
        context = self._context_for(state)
        updates: Dict[str, Any] = {}
        email_id = state.get("email_id")
        loaded_email = dict(state.get("loaded_email") or {})
        if email_id and (not loaded_email or loaded_email.get("id") != email_id):
            if context.gmail_client:
                loaded_email = context.gmail_client.get_message(email_id) or {}
            if not loaded_email:
                loaded_email = dict(state.get("email_metadata") or {})
                loaded_email.setdefault("id", email_id)
            updates["loaded_email"] = loaded_email
            updates["email_metadata"] = {**dict(state.get("email_metadata") or {}), **loaded_email}
            if loaded_email.get("threadId"):
                updates["email_thread_id"] = loaded_email.get("threadId")
        return updates

    def _load_policies_and_memory(self, state: AgentState) -> Dict[str, Any]:
        context = self._context_for(state)
        email_payload = state.get("loaded_email") or {}
        query = state.get("user_request") or email_payload.get("subject") or ""
        sender = email_payload.get("from") or state.get("email_metadata", {}).get("from")
        memory_context = self.memory_store.build_context(
            user_id=context.user_id,
            query=query,
            scope_hints=[sender, state.get("email_id"), state.get("email_thread_id")],
            limit=5,
        )
        return {
            "rules": context.rules,
            "automation_settings": context.automation_settings,
            "memory_context": memory_context,
            "demo_context": {
                **dict(state.get("demo_context") or {}),
                "anchored_email_id": email_payload.get("id"),
                "event_request": dict(email_payload.get("event_request") or {}),
            },
            "max_steps": self.max_steps,
        }

    def _agent_decide(self, state: AgentState) -> Dict[str, Any]:
        context = self._context_for(state)
        current_step = int(state.get("current_step") or 0)
        if current_step >= int(state.get("max_steps") or self.max_steps):
            decision: AgentDecision = {
                "action": "finish",
                "tool_name": None,
                "tool_args": {},
                "response_text": "Stopped because the agent reached its step limit.",
                "reason": "Guardrail against unbounded loops.",
                "confidence": 1.0,
            }
        else:
            try:
                decision = dict(self.decision_engine.decide(state, context, self.tool_registry))
            except Exception as exc:
                if self.decision_engine is self._heuristic_engine:
                    raise
                logger.exception(
                    "Primary decision engine failed for thread %s; falling back to heuristics: %s",
                    state.get("thread_id"),
                    exc,
                )
                decision = dict(self._heuristic_engine.decide(state, context, self.tool_registry))
                decision.setdefault(
                    "reason",
                    "Primary decision engine failed, so the runtime fell back to the heuristic controller.",
                )
            decision.setdefault("tool_args", {})
            decision.setdefault("action", "finish")
            decision.setdefault("confidence", 0.0)
            decision.setdefault("response_text", "")
            decision.setdefault("reason", "")
            if decision.get("action") == "tool" and decision.get("tool_name") not in self.tool_registry:
                decision = {
                    "action": "finish",
                    "tool_name": None,
                    "tool_args": {},
                    "response_text": f"Unknown tool requested: {decision.get('tool_name')}",
                    "reason": "The selected tool is not registered.",
                    "confidence": 1.0,
                }
        self.run_store.append(
            state["thread_id"],
            "decision",
            {
                "step": current_step + 1,
                "decision": decision,
            },
        )
        self._append_timeline(
            state["thread_id"],
            "next_action_selected",
            {
                "tool_name": decision.get("tool_name"),
                "action": decision.get("action"),
                "message": (
                    f"Selected {decision.get('tool_name')}."
                    if decision.get("action") == "tool"
                    else decision.get("work_item_title") or decision.get("response_text") or "Selected the next step."
                ),
            },
        )
        return {
            "pending_decision": decision,
            "current_step": current_step + 1,
        }

    def _route_after_decide(self, state: AgentState) -> str:
        decision = state.get("pending_decision") or {}
        if decision.get("action") == "work_item":
            return "handle_work_item"
        if decision.get("action") != "tool" or not decision.get("tool_name"):
            return "write_memory_candidates"
        return "risk_gate"

    def _handle_work_item(self, state: AgentState) -> Dict[str, Any]:
        decision = state.get("pending_decision") or {}
        step = int(state.get("current_step") or 0)
        item_type = str(decision.get("work_item_type") or "approval")
        existing = self.work_item_store.find_pending(
            thread_id=state["thread_id"],
            item_type=item_type,
            step=step,
        )
        if existing:
            work_item = existing
        else:
            work_item = self.work_item_store.create(
                thread_id=state["thread_id"],
                type=item_type,
                step=step,
                script_id=state.get("script_id"),
                title=decision.get("work_item_title") or item_type.replace("_", " ").title(),
                question=decision.get("work_item_question") or "Input required.",
                context=decision.get("work_item_context") or {},
                allowed_actions=decision.get("allowed_actions") or WorkItemStore.default_allowed_actions(item_type),
                allowed_responses=decision.get("allowed_responses") or [],
                blocking=True,
            )
            self.run_store.append(
                state["thread_id"],
                "work_item_created",
                {"work_item_id": work_item["id"], "type": item_type},
            )
            self._append_timeline(
                state["thread_id"],
                "needs_input",
                {
                    "message": decision.get("work_item_question") or "Input required.",
                    "work_item_id": work_item["id"],
                    "work_item_type": item_type,
                },
            )
            self.thread_store.update(state["thread_id"], status="needs_input", active_work_item_id=work_item["id"])

        response = interrupt(
            {
                "work_item_id": work_item["id"],
                "work_item_type": item_type,
                "title": work_item.get("title"),
                "question": work_item.get("question"),
                "context": work_item.get("context") or {},
                "allowed_actions": work_item.get("allowed_actions") or [],
                "allowed_responses": work_item.get("allowed_responses") or [],
                "message": work_item.get("question") or "Input required.",
            }
        )
        response = dict(response or {})
        action = str(response.get("action") or "").strip().lower()
        payload = dict(response.get("payload") or {})
        if action not in list(work_item.get("allowed_actions") or []):
            raise ValueError(f"Action {action} is not allowed for work item {work_item['id']}")

        self.work_item_store.resolve(work_item["id"], resolution={"action": action, "payload": payload})
        updated_demo_context = dict(state.get("demo_context") or {})
        if item_type == "conflict_decision":
            updated_demo_context["conflict_choice"] = payload.get("choice")
            updated_demo_context["conflict_event"] = dict((work_item.get("context") or {}).get("current_event") or {})
            updated_demo_context["new_request"] = dict((work_item.get("context") or {}).get("new_request") or {})
        if item_type == "draft_review":
            updated_demo_context["reviewed_draft"] = {
                **dict((work_item.get("context") or {})),
                **payload,
            }

        self.thread_store.update(state["thread_id"], status="in_progress", active_work_item_id=None)
        self.run_store.append(
            state["thread_id"],
            "work_item_resolved",
            {"work_item_id": work_item["id"], "type": item_type, "action": action},
        )
        return {
            "pending_work_item_id": work_item["id"],
            "last_user_response": {
                "work_item_id": work_item["id"],
                "type": item_type,
                "action": action,
                "payload": payload,
                "context": work_item.get("context") or {},
            },
            "demo_context": updated_demo_context,
        }

    def _find_or_create_approval(self, state: AgentState, tool: AgentTool) -> Dict[str, Any]:
        decision = state.get("pending_decision") or {}
        existing = self.approval_store.find_pending(
            thread_id=state["thread_id"],
            tool_name=tool.name,
            step=int(state.get("current_step") or 0),
        )
        if existing:
            return existing
        approval = self.approval_store.create(
            thread_id=state["thread_id"],
            user_id=state.get("user_id"),
            source=self._context_for(state).source,
            step=int(state.get("current_step") or 0),
            title=f"Approve {tool.name}",
            question=f"Approve running {tool.name}?",
            tool_name=tool.name,
            tool_args=decision.get("tool_args") or {},
            risk_level=tool.risk_level,
            reason=decision.get("reason") or "",
            confidence=decision.get("confidence") or 0.0,
            agent_kind=state.get("agent_kind"),
            context={
                "tool_name": tool.name,
                "tool_args": decision.get("tool_args") or {},
                "reason": decision.get("reason") or "",
            },
            allowed_actions=["approve", "reject", "edit"],
        )
        self.run_store.append(
            state["thread_id"],
            "approval_requested",
            {
                "approval_id": approval["id"],
                "tool_name": tool.name,
                "tool_args": decision.get("tool_args") or {},
                "risk_level": tool.risk_level,
            },
        )
        return approval

    def _risk_gate(self, state: AgentState) -> Dict[str, Any]:
        context = self._context_for(state)
        decision = state.get("pending_decision") or {}
        tool = self.tool_registry[decision["tool_name"]]
        if (
            state.get("thread_kind") == "official"
            and state.get("script_id") == "flagship_conflict"
            and tool.name in {"delete_calendar_event", "create_draft"}
        ):
            return {}
        requires_approval = should_require_approval(
            mode=context.mode,
            risk_level=tool.risk_level,
            confidence=float(decision.get("confidence") or 0.0),
            min_confidence=self.min_confidence,
            auto_write_risk_limit=self.auto_write_risk_limit,
            shadow_mode=context.shadow_mode,
        )
        if not requires_approval:
            return {}

        approval = self._find_or_create_approval(state, tool)
        response = interrupt(
            {
                "work_item_id": approval["id"],
                "work_item_type": "approval",
                "approval_id": approval["id"],
                "title": approval.get("title"),
                "question": approval.get("question"),
                "context": approval.get("context") or {},
                "allowed_actions": approval.get("allowed_actions") or ["approve", "reject", "edit"],
                "message": f"Approval required before running {tool.name}.",
            }
        )

        if isinstance(response, str):
            response = {"decision": response}
        response = dict(response or {})
        action = str(response.get("decision") or response.get("action") or "approve").strip().lower()
        payload = dict(response.get("payload") or {})

        if action == "reject":
            self.approval_store.update(approval["id"], status="rejected", resolution={"action": action, "payload": payload})
            self.thread_store.update(state["thread_id"], status="ready", active_work_item_id=None)
            self.run_store.append(
                state["thread_id"],
                "approval_rejected",
                {"approval_id": approval["id"], "tool_name": tool.name},
            )
            return {
                "final_outcome": {
                    "message": f"Action rejected before running {tool.name}.",
                    "tool_calls": [],
                    "success": True,
                    "thread_id": state["thread_id"],
                },
                "approvals": list(state.get("approvals") or []) + [approval["id"]],
            }

        new_args = dict(decision.get("tool_args") or {})
        if action == "edit":
            if isinstance(response.get("tool_args"), dict):
                new_args.update(response["tool_args"])
            if isinstance(payload.get("tool_args"), dict):
                new_args.update(payload["tool_args"])
        self.approval_store.update(approval["id"], status="approved", resolution={"action": action, "payload": payload}, tool_args=new_args)
        self.thread_store.update(state["thread_id"], status="in_progress", active_work_item_id=None)
        self.run_store.append(
            state["thread_id"],
            "approval_approved",
            {"approval_id": approval["id"], "tool_name": tool.name, "decision": action},
        )
        updated_decision = dict(decision)
        updated_decision["tool_args"] = new_args
        return {
            "pending_decision": updated_decision,
            "approvals": list(state.get("approvals") or []) + [approval["id"]],
        }

    def _route_after_risk_gate(self, state: AgentState) -> str:
        if state.get("final_outcome"):
            return "write_memory_candidates"
        return "execute_tool"

    def _derive_memory_candidates(
        self,
        state: AgentState,
        tool_name: str,
        result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if tool_name == "summarize_email" and result.get("summary"):
            candidates.append(
                {
                    "type": "episodic",
                    "scope": "thread",
                    "scope_id": state.get("email_id") or state.get("thread_id"),
                    "content": result["summary"],
                    "confidence": 0.72,
                    "source": "summarize_email",
                }
            )
        request = state.get("user_request") or ""
        if request and any(token in request.lower() for token in ("prefer", "usually", "always", "never")):
            candidates.append(
                {
                    "type": "semantic",
                    "scope": "user",
                    "scope_id": state.get("user_id"),
                    "content": request,
                    "confidence": 0.6,
                    "source": "chat_preference",
                }
            )
        return candidates

    def _execute_tool(self, state: AgentState) -> Dict[str, Any]:
        context = self._context_for(state)
        decision = state.get("pending_decision") or {}
        tool = self.tool_registry[decision["tool_name"]]
        args = dict(decision.get("tool_args") or {})
        self._append_timeline(state["thread_id"], "tool_started", {"tool_name": tool.name, "tool_args": args})
        result = tool.run(context, state, args)
        record = {
            "tool_name": tool.name,
            "tool_args": args,
            "risk_level": tool.risk_level,
            "result": result,
            "executed_at": _utc_now(),
        }
        completed_actions = list(state.get("completed_actions") or [])
        completed_actions.append(tool.name)
        memory_candidates = list(state.get("memory_candidates") or [])
        memory_candidates.extend(self._derive_memory_candidates(state, tool.name, result))
        self.run_store.append(
            state["thread_id"],
            "tool_executed",
            {"tool_name": tool.name, "result": result},
        )
        self._append_timeline(
            state["thread_id"],
            "tool_finished",
            {"tool_name": tool.name, "result": {"success": result.get("success"), "count": result.get("count")}},
        )
        if context.log_callback:
            context.log(f"Agent executed {tool.name}", "info")
        return {
            "last_tool_result": result,
            "tool_history": _tool_history(state) + [record],
            "completed_actions": completed_actions,
            "memory_candidates": memory_candidates,
        }

    def _reflect_on_result(self, state: AgentState) -> Dict[str, Any]:
        last_tool = _last_tool_name(state)
        last_result = state.get("last_tool_result") or {}
        updates: Dict[str, Any] = {}
        demo_context = dict(state.get("demo_context") or {})
        if last_tool == "read_email" and last_result.get("id"):
            updates["loaded_email"] = last_result
            updates["email_id"] = last_result.get("id")
        if last_tool == "summarize_email":
            updates["summary"] = last_result.get("summary") or ""
        if last_tool == "list_calendar_events":
            proposal = dict((state.get("loaded_email") or {}).get("event_request") or demo_context.get("event_request") or {})
            if proposal:
                conflict_event = _overlapping_event(proposal, last_result.get("events") or [])
                if conflict_event:
                    demo_context["conflict_event"] = conflict_event
                    updates["demo_context"] = demo_context
        if last_tool == "create_draft":
            demo_context["saved_draft"] = {
                "draft_id": last_result.get("draft_id"),
                "subject": last_result.get("subject"),
                "to": last_result.get("to"),
            }
            updates["demo_context"] = demo_context
        return updates

    def _route_after_reflection(self, state: AgentState) -> str:
        if state.get("final_outcome"):
            return "write_memory_candidates"
        return "agent_decide"

    def _write_memory_candidates(self, state: AgentState) -> Dict[str, Any]:
        candidates = list(state.get("memory_candidates") or [])
        if not candidates:
            return {}
        written = self.memory_store.write_candidates(
            user_id=state.get("user_id") or "unknown",
            thread_id=state["thread_id"],
            candidates=candidates,
        )
        if written:
            self.run_store.append(
                state["thread_id"],
                "memory_written",
                {"count": len(written)},
            )
        return {}

    def _format_tool_calls(self, state: AgentState) -> List[Dict[str, Any]]:
        return [
            {
                "tool_name": record.get("tool_name"),
                "arguments": record.get("tool_args") or {},
                "result": record.get("result") or {},
            }
            for record in _tool_history(state)
        ]

    def _build_chat_outcome(self, state: AgentState) -> Dict[str, Any]:
        tool_calls = self._format_tool_calls(state)
        decision = state.get("pending_decision") or {}
        last_tool = _last_tool_name(state)
        last_result = state.get("last_tool_result") or {}
        message = decision.get("response_text") or ""
        if not message:
            message = "Done."
            if last_tool == "create_calendar_event":
                event = last_result.get("event") or {}
                message = f"Created calendar event '{event.get('title') or 'Untitled Event'}'."
            elif last_tool == "create_draft":
                message = f"Created a draft email with subject '{last_result.get('subject') or ''}'."
            elif last_tool == "summarize_email":
                message = last_result.get("summary") or message
            elif last_tool in {"search_emails", "list_recent_emails"}:
                message = last_result.get("message") or message
            elif last_tool == "read_email":
                message = _message_excerpt(last_result.get("body") or last_result.get("snippet") or "", 320) or "I read the email."
            elif last_tool == "list_calendar_events":
                message = f"Found {last_result.get('count', 0)} events in that range."
        return {
            "message": message,
            "tool_calls": tool_calls,
            "success": True,
            "thread_id": state["thread_id"],
            "thread_status": _official_script_final_status(state),
            "timeline": self.timeline_store.list(state["thread_id"]),
            "thread": self.thread_store.get(state["thread_id"]),
        }

    def _build_triage_outcome(self, state: AgentState) -> Dict[str, Any]:
        tool_calls = self._format_tool_calls(state)
        labels_applied = sum(1 for item in tool_calls if item.get("tool_name") == "apply_label" and (item.get("result") or {}).get("success"))
        proposals_queued = sum(1 for item in tool_calls if item.get("tool_name") == "queue_event_proposal" and (item.get("result") or {}).get("success"))
        events_created = sum(1 for item in tool_calls if item.get("tool_name") == "create_calendar_event" and (item.get("result") or {}).get("success"))
        return {
            "message": state.get("summary") or "Email triage completed.",
            "tool_calls": tool_calls,
            "success": True,
            "thread_id": state["thread_id"],
            "labels_applied": labels_applied,
            "proposals_queued": proposals_queued,
            "events_created": events_created,
            "thread_status": _official_script_final_status(state),
            "timeline": self.timeline_store.list(state["thread_id"]),
            "thread": self.thread_store.get(state["thread_id"]),
        }

    def _finalize(self, state: AgentState) -> Dict[str, Any]:
        if state.get("final_outcome"):
            return {}
        if state.get("agent_kind") == "triage":
            outcome = self._build_triage_outcome(state)
        else:
            outcome = self._build_chat_outcome(state)
        self.run_store.append(
            state["thread_id"],
            "finalized",
            {"success": outcome.get("success"), "message": outcome.get("message")},
        )
        self._append_timeline(
            state["thread_id"],
            "completed",
            {"message": outcome.get("message") or "Completed."},
        )
        outcome["timeline"] = self.timeline_store.list(state["thread_id"])
        outcome["thread"] = self.thread_store.get(state["thread_id"])
        return {"final_outcome": outcome}

    def _format_interrupt_payload(self, thread_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = payload.get("tool_name") or ((payload.get("context") or {}).get("tool_name"))
        tool_args = payload.get("tool_args") or ((payload.get("context") or {}).get("tool_args")) or {}
        work_item_id = payload.get("work_item_id") or payload.get("approval_id")
        work_item_type = payload.get("work_item_type") or "approval"
        question = payload.get("question") or payload.get("message") or f"Approval required before running {tool_name}."
        return {
            "message": question,
            "tool_calls": [
                {
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "result": {
                        "success": True,
                        "result": {
                            "requires_input": True,
                            "work_item_id": work_item_id,
                            "work_item_type": work_item_type,
                            "allowed_actions": payload.get("allowed_actions") or [],
                            "allowed_responses": payload.get("allowed_responses") or [],
                            "reason": payload.get("reason") or ((payload.get("context") or {}).get("reason")),
                        },
                    },
                }
            ],
            "success": True,
            "pending_work_item": True,
            "pending_approval": work_item_type == "approval",
            "work_item_id": work_item_id,
            "approval_id": work_item_id if work_item_type == "approval" else None,
            "work_item": self.work_item_store.get(work_item_id) if work_item_id else None,
            "thread": self.thread_store.get(thread_id),
            "timeline": self.timeline_store.list(thread_id),
            "thread_id": thread_id,
        }
