from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict


RiskLevel = Literal["read_only", "reversible", "external_write", "destructive"]
AgentMode = Literal["auto", "semi_auto"]
AgentKind = Literal["triage", "chat"]
ThreadKind = Literal["official", "free"]
ThreadStatus = Literal["ready", "in_progress", "needs_input", "completed"]


class AgentDecision(TypedDict, total=False):
    action: Literal["tool", "finish", "work_item"]
    tool_name: Optional[str]
    tool_args: Dict[str, Any]
    response_text: str
    reason: str
    confidence: float
    work_item_type: str
    work_item_title: str
    work_item_question: str
    work_item_context: Dict[str, Any]
    allowed_actions: List[str]
    allowed_responses: List[str]
    stable_status: ThreadStatus


class ToolRecord(TypedDict, total=False):
    tool_name: str
    tool_args: Dict[str, Any]
    risk_level: RiskLevel
    result: Dict[str, Any]
    executed_at: str


class MemoryCandidate(TypedDict, total=False):
    type: Literal["semantic", "episodic", "procedural"]
    scope: Literal["user", "contact", "thread"]
    content: str
    confidence: float
    source: str
    scope_id: Optional[str]


class AgentState(TypedDict, total=False):
    thread_id: str
    thread_kind: ThreadKind
    thread_title: str
    script_id: Optional[str]
    agent_kind: AgentKind
    user_id: str
    mode: AgentMode
    shadow_mode: bool
    email_id: Optional[str]
    email_thread_id: Optional[str]
    email_metadata: Dict[str, Any]
    loaded_email: Dict[str, Any]
    user_request: Optional[str]
    recent_messages: List[Dict[str, str]]
    summary: str
    memory_context: Dict[str, Any]
    demo_context: Dict[str, Any]
    rules: List[Dict[str, Any]]
    automation_settings: Dict[str, Any]
    current_step: int
    max_steps: int
    pending_decision: AgentDecision
    pending_work_item_id: Optional[str]
    last_user_response: Dict[str, Any]
    last_tool_result: Dict[str, Any]
    tool_history: List[ToolRecord]
    completed_actions: List[str]
    memory_candidates: List[MemoryCandidate]
    final_outcome: Dict[str, Any]
    errors: List[str]
    approvals: List[str]


@dataclass
class InvocationContext:
    thread_id: str
    user_id: str
    agent_kind: AgentKind
    mode: AgentMode
    shadow_mode: bool
    source: str
    thread_kind: ThreadKind = "free"
    script_id: Optional[str] = None
    thread_title: Optional[str] = None
    gmail_client: Any = None
    gcal_client: Any = None
    llm_client: Any = None
    rules: List[Dict[str, Any]] = field(default_factory=list)
    automation_settings: Dict[str, Any] = field(default_factory=dict)
    log_callback: Optional[Callable[[str, str], None]] = None
    proposal_writer: Optional[Callable[[Dict[str, Any], str, str, str], Dict[str, Any]]] = None
    proposal_status_updater: Optional[Callable[[str, str], Optional[Dict[str, Any]]]] = None

    def log(self, message: str, level: str = "info") -> None:
        if self.log_callback:
            self.log_callback(message, level)
