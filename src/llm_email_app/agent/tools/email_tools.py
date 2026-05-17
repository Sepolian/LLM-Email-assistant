from __future__ import annotations

from typing import Any, Dict, List

from llm_email_app.agent.state import AgentState, InvocationContext
from llm_email_app.agent.tools.base import AgentTool
from llm_email_app.email.gmail_client import canonical_folder_key


QUERY_ALIASES = {
    "预算": "budget",
    "财务": "finance",
    "日程": "schedule",
    "会议": "meeting",
    "路线图": "roadmap",
    "客户": "client",
    "彩排": "rehearsal",
    "上线": "launch",
    "发布": "launch",
    "出差": "travel",
    "旅行": "travel",
    "面试": "interview",
    "招聘": "hiring",
    "回复": "reply",
    "草稿": "draft",
}


def _query_variants(query: str) -> List[str]:
    lowered = (query or "").strip().lower()
    variants = [lowered] if lowered else []
    for source, target in QUERY_ALIASES.items():
        if source in query and target not in variants:
            variants.append(target)
    return variants


def _simple_search(items: List[Dict[str, Any]], query: str, limit: int) -> List[Dict[str, Any]]:
    variants = _query_variants(query)
    if not variants:
        return items[:limit]
    matches: List[Dict[str, Any]] = []
    for item in items:
        haystack = " ".join([
            str(item.get("from") or ""),
            str(item.get("subject") or ""),
            str(item.get("snippet") or ""),
            str(item.get("body") or ""),
            " ".join(item.get("labels") or []),
        ]).lower()
        if any(variant and variant in haystack for variant in variants):
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def build_email_tools() -> Dict[str, AgentTool]:
    def list_recent_emails(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gmail_client is None:
            return {"success": False, "error": "Gmail client is not configured"}
        limit = max(1, min(int(args.get("limit") or args.get("max_results") or 10), 20))
        days = max(1, min(int(args.get("days") or 14), 90))
        folder = canonical_folder_key(args.get("folder") or "inbox")
        mailbox = context.gmail_client.fetch_mailbox_overview(
            active_folder=folder,
            page=1,
            per_page=limit,
            days=days,
        )
        emails = mailbox.get("folders", {}).get(folder, {}).get("items", [])
        return {
            "success": True,
            "emails": emails,
            "folder": folder,
            "count": len(emails),
            "message": f"Found {len(emails)} recent emails in {folder}.",
        }

    def search_emails(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gmail_client is None:
            return {"success": False, "error": "Gmail client is not configured"}
        query = (args.get("query") or args.get("q") or "").strip()
        limit = max(1, min(int(args.get("limit") or args.get("max_results") or 10), 20))
        days = max(1, min(int(args.get("days") or 14), 90))
        candidates = context.gmail_client.fetch_emails_since(days=days, max_results=limit * 5)
        emails = _simple_search(candidates, query, limit)
        return {
            "success": True,
            "query": query,
            "emails": emails,
            "count": len(emails),
            "message": f"Found {len(emails)} emails for '{query}'.",
        }

    def read_email(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gmail_client is None:
            return {"success": False, "error": "Gmail client is not configured"}
        email_id = args.get("email_id") or state.get("email_id")
        if not email_id:
            return {"success": False, "error": "email_id is required"}
        email_payload = context.gmail_client.get_message(email_id)
        if not email_payload:
            return {"success": False, "error": f"Email {email_id} was not found"}
        return {"success": True, **email_payload}

    def apply_label(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gmail_client is None:
            return {"success": False, "error": "Gmail client is not configured"}
        message_id = args.get("message_id") or state.get("email_id")
        if not message_id:
            return {"success": False, "error": "message_id is required"}

        labels = list(args.get("labels") or [])
        rule_ids = list(args.get("rule_ids") or [])
        if args.get("rule_id"):
            rule_ids.append(args["rule_id"])
        if not labels and rule_ids:
            for rule_id in rule_ids:
                rule = next((item for item in context.rules if item.get("id") == rule_id), None)
                if rule and rule.get("label"):
                    labels.append(rule["label"])
        if not labels:
            return {"success": False, "error": "No labels resolved for apply_label"}

        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "message_id": message_id,
                "labels": labels,
                "message": f"Shadow mode: would apply {len(labels)} labels.",
            }

        label_ids = []
        for label in labels:
            label_ids.append(context.gmail_client.check_or_create_label(label))
        success = context.gmail_client.apply_labels_to_message(message_id, label_ids)
        return {
            "success": bool(success),
            "message_id": message_id,
            "labels": labels,
            "label_ids": label_ids,
        }

    def create_draft(context: InvocationContext, state: AgentState, args: Dict[str, Any]) -> Dict[str, Any]:
        if context.gmail_client is None:
            return {"success": False, "error": "Gmail client is not configured"}
        to = (args.get("to") or "").strip()
        subject = (args.get("subject") or "").strip()
        body = (args.get("body") or "").strip()
        reply_to_message_id = args.get("reply_to_message_id")
        if not to or not subject:
            return {"success": False, "error": "Both to and subject are required"}

        if context.shadow_mode:
            return {
                "success": True,
                "shadow_mode": True,
                "draft_id": "shadow-draft-id",
                "to": to,
                "subject": subject,
                "reply_to_message_id": reply_to_message_id,
            }

        draft = context.gmail_client.create_draft(
            to=to,
            subject=subject,
            body=body,
            reply_to_message_id=reply_to_message_id,
        )
        if not draft:
            return {"success": False, "error": "Failed to create draft"}
        return {
            "success": True,
            "draft_id": draft.get("id"),
            "message_id": (draft.get("message") or {}).get("id"),
            "to": to,
            "subject": subject,
            "reply_to_message_id": reply_to_message_id,
        }

    return {
        "list_recent_emails": AgentTool(
            name="list_recent_emails",
            description="List recent emails from a mailbox folder.",
            risk_level="read_only",
            dry_run_supported=True,
            func=list_recent_emails,
        ),
        "search_emails": AgentTool(
            name="search_emails",
            description="Search recent emails by sender, subject, snippet, or body text.",
            risk_level="read_only",
            dry_run_supported=True,
            func=search_emails,
        ),
        "read_email": AgentTool(
            name="read_email",
            description="Read the full content of one email.",
            risk_level="read_only",
            dry_run_supported=True,
            func=read_email,
        ),
        "apply_label": AgentTool(
            name="apply_label",
            description="Apply one or more labels to an email.",
            risk_level="reversible",
            dry_run_supported=True,
            func=apply_label,
        ),
        "create_draft": AgentTool(
            name="create_draft",
            description="Create a draft email or draft reply in Gmail.",
            risk_level="external_write",
            dry_run_supported=True,
            func=create_draft,
        ),
    }
