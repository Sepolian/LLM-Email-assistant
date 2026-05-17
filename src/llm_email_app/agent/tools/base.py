from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from llm_email_app.agent.state import AgentState, InvocationContext, RiskLevel


ToolCallable = Callable[[InvocationContext, AgentState, Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    risk_level: RiskLevel
    dry_run_supported: bool
    func: ToolCallable

    def run(self, context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        return self.func(context, state, args)
