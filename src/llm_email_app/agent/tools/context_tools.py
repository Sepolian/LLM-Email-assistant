from __future__ import annotations

from typing import Any, Dict

from llm_email_app.agent.memory.store import MarkdownMemoryStore
from llm_email_app.agent.state import AgentState, InvocationContext
from llm_email_app.agent.tools.base import AgentTool


def _resolve_email(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
    email_id = args.get("email_id") or state.get("email_id")
    loaded = state.get("loaded_email") or {}
    if loaded and loaded.get("id") == email_id:
        return loaded
    if email_id and context.gmail_client:
        return context.gmail_client.get_message(email_id) or {}
    return loaded


def build_context_tools(memory_store: MarkdownMemoryStore) -> Dict[str, AgentTool]:
    def summarize_email(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        llm_client = context.llm_client
        if llm_client is None:
            return {"success": False, "error": "LLM client is not configured"}
        email_payload = _resolve_email(context, state, args)
        body = email_payload.get("html") or email_payload.get("body") or email_payload.get("snippet") or ""
        sender = email_payload.get("from") or ""
        received = email_payload.get("received")
        subject = email_payload.get("subject") or state.get("email_metadata", {}).get("subject") or ""
        result = llm_client.summarize_email(
            email_body=body,
            email_received_time=received,
            email_sender=sender,
        )
        return {
            "success": True,
            "summary": result.get("text") or "",
            "proposals": result.get("proposals") or [],
            "draft_reply": result.get("draft_reply"),
            "email_id": email_payload.get("id") or state.get("email_id"),
            "subject": subject,
        }

    def evaluate_label_rules(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        llm_client = context.llm_client
        if llm_client is None:
            return {"success": False, "error": "LLM client is not configured"}
        email_payload = _resolve_email(context, state, args)
        matches = llm_client.evaluate_label_rules(
            email_body=email_payload.get("html") or email_payload.get("body") or email_payload.get("snippet") or "",
            subject=email_payload.get("subject") or "",
            sender=email_payload.get("from") or "",
            rules=context.rules,
        )
        return {
            "success": True,
            "matches": matches.get("matches") or [],
            "rule_count": len(context.rules),
            "email_id": email_payload.get("id") or state.get("email_id"),
        }

    def search_memory(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        query = (args.get("query") or state.get("user_request") or "").strip()
        notes = memory_store.search(
            user_id=context.user_id,
            query=query,
            scope=args.get("scope"),
            scope_id=args.get("scope_id"),
            limit=int(args.get("limit") or 5),
        )
        return {
            "success": True,
            "query": query,
            "notes": notes,
            "count": len(notes),
        }

    return {
        "summarize_email": AgentTool(
            name="summarize_email",
            description="Summarize an email and extract scheduling proposals or draft replies.",
            risk_level="read_only",
            dry_run_supported=True,
            func=summarize_email,
        ),
        "evaluate_label_rules": AgentTool(
            name="evaluate_label_rules",
            description="Evaluate the current email against configured auto-label rules.",
            risk_level="read_only",
            dry_run_supported=True,
            func=evaluate_label_rules,
        ),
        "search_memory": AgentTool(
            name="search_memory",
            description="Retrieve long-term markdown memory relevant to the current task.",
            risk_level="read_only",
            dry_run_supported=True,
            func=search_memory,
        ),
    }
