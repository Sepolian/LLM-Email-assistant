"""MCP Server for Email Operations.

This module implements a Model Context Protocol (MCP) server that exposes
email operations as tools that can be called by LLMs.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MCPEmailServer:
    """MCP Server that provides email tools for LLM function calling."""
    
    def __init__(self, gmail_client=None, email_cache_loader=None):
        """Initialize the MCP server with an optional Gmail client.
        
        Args:
            gmail_client: An instance of GmailClient for email operations
            email_cache_loader: A callable that returns cached emails
        """
        self.gmail_client = gmail_client
        self.email_cache_loader = email_cache_loader
        self.tools = self._define_tools()
    
    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define the tools available to the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_emails",
                    "description": "Search for emails in the user's mailbox. Use this to find specific emails by sender, subject, content, or date. Returns matching emails from the cached email list.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query - can be sender name/email, subject keywords, or content keywords"
                            },
                            "sender": {
                                "type": "string",
                                "description": "Filter by sender email address or name"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Filter by subject line (partial match)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of emails to return (default: 5)"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Only search emails from the last N days (default: 14)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_email",
                    "description": "Read the full content of a specific email by its ID. Use this to get the complete body and details of an email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {
                                "type": "string",
                                "description": "The unique ID of the email to read"
                            }
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_recent_emails",
                    "description": "List the most recent emails in the inbox. Use this to show the user their latest emails.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of emails to return (default: 10)"
                            },
                            "folder": {
                                "type": "string",
                                "description": "Folder to list emails from: 'inbox', 'sent', 'drafts', 'trash' (default: 'inbox')"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "draft_reply",
                    "description": "Create a draft reply to an email. Use this when the user wants to compose a reply to a specific email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {
                                "type": "string",
                                "description": "The ID of the email to reply to"
                            },
                            "body": {
                                "type": "string",
                                "description": "The body content of the reply email"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Optional subject line (defaults to 'Re: <original subject>')"
                            }
                        },
                        "required": ["email_id", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compose_draft",
                    "description": "Create a new draft email. Use this when the user wants to compose a new email (not a reply).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject line"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body content"
                            }
                        },
                        "required": ["to", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_email",
                    "description": "Get the content of an email for summarization. Use this to quickly understand the key points of a long email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {
                                "type": "string",
                                "description": "The ID of the email to summarize"
                            }
                        },
                        "required": ["email_id"]
                    }
                }
            }
        ]
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return the list of available tools for LLM function calling."""
        return self.tools
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments for the tool
            
        Returns:
            A dictionary with 'success' boolean and either 'result' or 'error'
        """
        try:
            if tool_name == "search_emails":
                return self._search_emails(arguments)
            elif tool_name == "read_email":
                return self._read_email(arguments)
            elif tool_name == "list_recent_emails":
                return self._list_recent_emails(arguments)
            elif tool_name == "draft_reply":
                return self._draft_reply(arguments)
            elif tool_name == "compose_draft":
                return self._compose_draft(arguments)
            elif tool_name == "summarize_email":
                return self._summarize_email(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.exception(f"Error executing tool {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_cached_emails(self, days_back: int = 14, limit: int = 100) -> List[Dict[str, Any]]:
        """Get emails from cache or fallback to gmail client."""
        if self.email_cache_loader:
            try:
                return self.email_cache_loader(days_back, limit)
            except Exception as e:
                logger.warning(f"Failed to load cached emails: {e}")
        
        if self.gmail_client:
            try:
                return self.gmail_client.fetch_emails_since(days=days_back, max_results=limit)
            except Exception as e:
                logger.warning(f"Failed to fetch emails from Gmail: {e}")
        
        return []
    
    def _search_emails(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search for emails matching the query."""
        query = args.get("query", "").lower()
        sender_filter = args.get("sender", "").lower()
        subject_filter = args.get("subject", "").lower()
        max_results = args.get("max_results", 5)
        days_back = args.get("days_back", 14)
        
        emails = self._get_cached_emails(days_back=days_back, limit=100)
        
        if not emails:
            return {
                "success": True,
                "result": {
                    "emails": [],
                    "count": 0,
                    "message": "No emails found in cache"
                }
            }
        
        matched = []
        for email in emails:
            # Extract fields
            email_from = (email.get("from") or "").lower()
            email_subject = (email.get("subject") or "").lower()
            email_body = (email.get("body") or email.get("snippet") or "").lower()
            
            # Check filters
            if sender_filter and sender_filter not in email_from:
                continue
            if subject_filter and subject_filter not in email_subject:
                continue
            if query:
                # General query matches any field
                if (query not in email_from and 
                    query not in email_subject and 
                    query not in email_body):
                    continue
            
            matched.append({
                "id": email.get("id"),
                "from": email.get("from"),
                "subject": email.get("subject"),
                "snippet": (email.get("snippet") or email.get("body", "")[:150] + "..."),
                "received": email.get("received"),
                "labels": email.get("labels", [])
            })
            
            if len(matched) >= max_results:
                break
        
        return {
            "success": True,
            "result": {
                "emails": matched,
                "count": len(matched),
                "message": f"Found {len(matched)} matching email(s)"
            }
        }
    
    def _read_email(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read the full content of an email."""
        email_id = args.get("email_id")
        
        if not email_id:
            return {"success": False, "error": "email_id is required"}
        
        # First try cache
        emails = self._get_cached_emails(days_back=30, limit=200)
        for email in emails:
            if email.get("id") == email_id:
                return {
                    "success": True,
                    "result": {
                        "id": email.get("id"),
                        "from": email.get("from"),
                        "to": email.get("to"),
                        "subject": email.get("subject"),
                        "body": email.get("body") or email.get("html") or email.get("snippet"),
                        "received": email.get("received"),
                        "labels": email.get("labels", [])
                    }
                }
        
        # Fallback to Gmail client if not in cache
        if self.gmail_client:
            try:
                email = self.gmail_client.get_message(email_id)
                if email:
                    return {
                        "success": True,
                        "result": {
                            "id": email.get("id"),
                            "from": email.get("from"),
                            "to": email.get("to"),
                            "subject": email.get("subject"),
                            "body": email.get("body") or email.get("html") or email.get("snippet"),
                            "received": email.get("received"),
                            "labels": email.get("labels", [])
                        }
                    }
            except Exception as e:
                logger.warning(f"Failed to fetch email {email_id}: {e}")
        
        return {"success": False, "error": f"Email {email_id} not found"}
    
    def _list_recent_emails(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List recent emails."""
        max_results = args.get("max_results", 10)
        folder = args.get("folder", "inbox")
        
        emails = self._get_cached_emails(days_back=14, limit=max_results * 2)
        
        # Filter by folder if specified
        if folder and folder != "inbox":
            filtered = [e for e in emails if e.get("folder") == folder]
            emails = filtered if filtered else emails
        
        # Sort by received date descending
        try:
            emails.sort(
                key=lambda x: x.get("received") or "",
                reverse=True
            )
        except Exception:
            pass
        
        recent = []
        for email in emails[:max_results]:
            recent.append({
                "id": email.get("id"),
                "from": email.get("from"),
                "subject": email.get("subject"),
                "snippet": (email.get("snippet") or email.get("body", "")[:100] + "..."),
                "received": email.get("received"),
                "is_read": "UNREAD" not in (email.get("label_ids") or [])
            })
        
        return {
            "success": True,
            "result": {
                "emails": recent,
                "count": len(recent),
                "folder": folder,
                "message": f"Showing {len(recent)} recent email(s) from {folder}"
            }
        }
    
    def _draft_reply(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a draft reply to an email."""
        email_id = args.get("email_id")
        body = args.get("body")
        subject = args.get("subject")
        
        if not email_id:
            return {"success": False, "error": "email_id is required"}
        if not body:
            return {"success": False, "error": "body is required"}
        
        # Get original email to find recipient
        original_email = None
        emails = self._get_cached_emails(days_back=30, limit=200)
        for email in emails:
            if email.get("id") == email_id:
                original_email = email
                break
        
        if not original_email and self.gmail_client:
            try:
                original_email = self.gmail_client.get_message(email_id)
            except Exception as e:
                logger.warning(f"Failed to fetch original email: {e}")
        
        if not original_email:
            return {"success": False, "error": f"Original email {email_id} not found"}
        
        # Extract sender to use as recipient
        to_address = original_email.get("from", "")
        # Handle "Name <email>" format
        if "<" in to_address and ">" in to_address:
            to_address = to_address[to_address.index("<")+1:to_address.index(">")]
        
        original_subject = original_email.get("subject", "")
        if not subject:
            subject = f"Re: {original_subject}" if not original_subject.startswith("Re:") else original_subject
        
        if self.gmail_client is None:
            return {
                "success": True,
                "result": {
                    "draft_id": f"stub-draft-{datetime.now(timezone.utc).timestamp()}",
                    "to": to_address,
                    "subject": subject,
                    "message": f"Draft reply would be created (stub mode)"
                }
            }
        
        try:
            result = self.gmail_client.create_draft(
                to=to_address,
                subject=subject,
                body=body,
                reply_to_message_id=email_id
            )
            if result:
                return {
                    "success": True,
                    "result": {
                        "draft_id": result.get("id"),
                        "to": to_address,
                        "subject": subject,
                        "message": f"Draft reply created successfully"
                    }
                }
            else:
                return {"success": False, "error": "Failed to create draft"}
        except Exception as e:
            return {"success": False, "error": f"Failed to create draft: {str(e)}"}
    
    def _compose_draft(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new draft email."""
        to = args.get("to")
        subject = args.get("subject")
        body = args.get("body")
        
        if not to:
            return {"success": False, "error": "to address is required"}
        if not subject:
            return {"success": False, "error": "subject is required"}
        if not body:
            return {"success": False, "error": "body is required"}
        
        if self.gmail_client is None:
            return {
                "success": True,
                "result": {
                    "draft_id": f"stub-draft-{datetime.now(timezone.utc).timestamp()}",
                    "to": to,
                    "subject": subject,
                    "message": "Draft would be created (stub mode)"
                }
            }
        
        try:
            result = self.gmail_client.create_draft(
                to=to,
                subject=subject,
                body=body
            )
            if result:
                return {
                    "success": True,
                    "result": {
                        "draft_id": result.get("id"),
                        "to": to,
                        "subject": subject,
                        "message": "Draft created successfully"
                    }
                }
            else:
                return {"success": False, "error": "Failed to create draft"}
        except Exception as e:
            return {"success": False, "error": f"Failed to create draft: {str(e)}"}
    
    def _summarize_email(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get email content for summarization."""
        email_id = args.get("email_id")
        
        if not email_id:
            return {"success": False, "error": "email_id is required"}
        
        # Get email content
        email = None
        emails = self._get_cached_emails(days_back=30, limit=200)
        for e in emails:
            if e.get("id") == email_id:
                email = e
                break
        
        if not email and self.gmail_client:
            try:
                email = self.gmail_client.get_message(email_id)
            except Exception as ex:
                logger.warning(f"Failed to fetch email for summary: {ex}")
        
        if not email:
            return {"success": False, "error": f"Email {email_id} not found"}
        
        # Return email content for LLM to summarize in its response
        body = email.get("body") or email.get("html") or email.get("snippet") or ""
        # Truncate if too long
        if len(body) > 4000:
            body = body[:4000] + "...[truncated]"
        
        return {
            "success": True,
            "result": {
                "id": email.get("id"),
                "from": email.get("from"),
                "subject": email.get("subject"),
                "received": email.get("received"),
                "body_preview": body,
                "message": "Email content retrieved. Please summarize the key points."
            }
        }
