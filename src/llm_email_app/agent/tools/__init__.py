from __future__ import annotations

from llm_email_app.agent.memory.store import MarkdownMemoryStore
from llm_email_app.agent.tools.base import AgentTool
from llm_email_app.agent.tools.calendar_tools import build_calendar_tools
from llm_email_app.agent.tools.context_tools import build_context_tools
from llm_email_app.agent.tools.email_tools import build_email_tools

def build_tool_registry(memory_store: MarkdownMemoryStore) -> Dict[str, AgentTool]:
    registry: Dict[str, AgentTool] = {}
    for group in (
        build_context_tools(memory_store),
        build_email_tools(),
        build_calendar_tools(),
    ):
        registry.update(group)
    return registry


__all__ = ["AgentTool", "build_tool_registry"]
