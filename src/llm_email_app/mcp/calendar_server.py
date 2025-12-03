"""MCP Server for Calendar Operations.

This module implements a Model Context Protocol (MCP) server that exposes
calendar operations as tools that can be called by LLMs.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class MCPCalendarServer:
    """MCP Server that provides calendar tools for LLM function calling."""
    
    def __init__(self, gcal_client=None):
        """Initialize the MCP server with an optional Google Calendar client.
        
        Args:
            gcal_client: An instance of GCalClient for calendar operations
        """
        self.gcal_client = gcal_client
        self.tools = self._define_tools()
    
    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define the tools available to the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_calendar_event",
                    "description": "Add a new event to the user's Google Calendar. Use this when the user wants to schedule a meeting, appointment, or any time-based event.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "The title/summary of the event (e.g., 'Team Meeting', 'Doctor Appointment')"
                            },
                            "date": {
                                "type": "string",
                                "description": "The date of the event in YYYY-MM-DD format (e.g., '2025-03-12')"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "The start time in HH:MM format (24-hour, e.g., '14:00' for 2pm)"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "The end time in HH:MM format (24-hour, e.g., '15:00'). If not specified, defaults to 1 hour after start."
                            },
                            "location": {
                                "type": "string",
                                "description": "The location of the event (e.g., 'SHB Room 101', 'Zoom')"
                            },
                            "description": {
                                "type": "string",
                                "description": "Additional notes or description for the event"
                            },
                            "attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of attendee email addresses"
                            }
                        },
                        "required": ["title", "date", "start_time"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_calendar_events",
                    "description": "List upcoming calendar events. Use this to check the user's schedule or find available times.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days_ahead": {
                                "type": "integer",
                                "description": "Number of days ahead to look for events (default: 7)"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of events to return (default: 10)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_calendar_event",
                    "description": "Delete a calendar event by its ID. Use this when the user wants to cancel or remove an event.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "The unique ID of the event to delete"
                            }
                        },
                        "required": ["event_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_calendar_event",
                    "description": "Update an existing calendar event. Use this to modify event details like time, location, or title.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "The unique ID of the event to update"
                            },
                            "title": {
                                "type": "string",
                                "description": "New title for the event"
                            },
                            "date": {
                                "type": "string",
                                "description": "New date in YYYY-MM-DD format"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "New start time in HH:MM format"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "New end time in HH:MM format"
                            },
                            "location": {
                                "type": "string",
                                "description": "New location"
                            },
                            "description": {
                                "type": "string",
                                "description": "New description"
                            }
                        },
                        "required": ["event_id"]
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
            if tool_name == "add_calendar_event":
                return self._add_event(arguments)
            elif tool_name == "list_calendar_events":
                return self._list_events(arguments)
            elif tool_name == "delete_calendar_event":
                return self._delete_event(arguments)
            elif tool_name == "update_calendar_event":
                return self._update_event(arguments)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.exception(f"Error executing tool {tool_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_datetime(self, date_str: str, time_str: str) -> str:
        """Parse date and time strings into ISO 8601 format with HK timezone.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format
            
        Returns:
            ISO 8601 datetime string with +08:00 timezone
        """
        # Parse the date and time
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        # Add Hong Kong timezone offset
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    def _add_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a calendar event."""
        title = args.get("title", "Untitled Event")
        date = args.get("date")
        start_time = args.get("start_time")
        end_time = args.get("end_time")
        location = args.get("location", "")
        description = args.get("description", "")
        attendees = args.get("attendees", [])
        
        if not date or not start_time:
            return {"success": False, "error": "Date and start_time are required"}
        
        # If no end time, default to 1 hour after start
        if not end_time:
            start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(hours=1)
            end_time = end_dt.strftime("%H:%M")
        
        start_iso = self._parse_datetime(date, start_time)
        end_iso = self._parse_datetime(date, end_time)
        
        proposal = {
            "title": title,
            "start": start_iso,
            "end": end_iso,
            "location": location,
            "notes": description,
            "attendees": attendees,
            "timeZone": "Asia/Hong_Kong"
        }
        
        if self.gcal_client is None:
            # Return stub result for testing
            return {
                "success": True,
                "result": {
                    "event_id": "stub-event-id",
                    "message": f"Event '{title}' would be created on {date} at {start_time}",
                    "event": proposal
                }
            }
        
        try:
            event_id = self.gcal_client.create_event(proposal)
            return {
                "success": True,
                "result": {
                    "event_id": event_id,
                    "message": f"Successfully created event '{title}' on {date} from {start_time} to {end_time}",
                    "event": {
                        "id": event_id,
                        "title": title,
                        "date": date,
                        "start_time": start_time,
                        "end_time": end_time,
                        "location": location
                    }
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create event: {str(e)}"}
    
    def _list_events(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List upcoming calendar events."""
        days_ahead = args.get("days_ahead", 7)
        max_results = args.get("max_results", 10)
        
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()
        
        if self.gcal_client is None:
            return {
                "success": True,
                "result": {
                    "events": [],
                    "message": "No calendar client configured"
                }
            }
        
        try:
            events = self.gcal_client.list_events(
                max_results=max_results,
                time_min=time_min,
                time_max=time_max
            )
            
            # Format events for display
            formatted_events = []
            for event in events:
                start = event.get("start", {})
                end = event.get("end", {})
                formatted_events.append({
                    "id": event.get("id"),
                    "title": event.get("summary", "Untitled"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "location": event.get("location", ""),
                })
            
            return {
                "success": True,
                "result": {
                    "events": formatted_events,
                    "count": len(formatted_events),
                    "message": f"Found {len(formatted_events)} events in the next {days_ahead} days"
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to list events: {str(e)}"}
    
    def _delete_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a calendar event."""
        event_id = args.get("event_id")
        
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        
        if self.gcal_client is None:
            return {
                "success": True,
                "result": {"message": f"Event {event_id} would be deleted"}
            }
        
        try:
            success = self.gcal_client.delete_event(event_id)
            if success:
                return {
                    "success": True,
                    "result": {"message": f"Successfully deleted event {event_id}"}
                }
            else:
                return {"success": False, "error": "Failed to delete event"}
        except Exception as e:
            return {"success": False, "error": f"Failed to delete event: {str(e)}"}
    
    def _update_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update a calendar event."""
        event_id = args.get("event_id")
        
        if not event_id:
            return {"success": False, "error": "event_id is required"}
        
        updates = {}
        
        if "title" in args:
            updates["title"] = args["title"]
        if "description" in args:
            updates["notes"] = args["description"]
        if "location" in args:
            updates["location"] = args["location"]
        
        # Handle date/time updates
        if "date" in args and "start_time" in args:
            updates["start"] = self._parse_datetime(args["date"], args["start_time"])
            if "end_time" in args:
                updates["end"] = self._parse_datetime(args["date"], args["end_time"])
        
        if self.gcal_client is None:
            return {
                "success": True,
                "result": {
                    "message": f"Event {event_id} would be updated",
                    "updates": updates
                }
            }
        
        try:
            updated_id = self.gcal_client.update_event(event_id, updates)
            if updated_id:
                return {
                    "success": True,
                    "result": {
                        "event_id": updated_id,
                        "message": f"Successfully updated event {event_id}"
                    }
                }
            else:
                return {"success": False, "error": "Failed to update event"}
        except Exception as e:
            return {"success": False, "error": f"Failed to update event: {str(e)}"}


class MCPChatHandler:
    """Handles chat interactions with MCP tool calling."""
    
    def __init__(self, llm_client, mcp_server: MCPCalendarServer):
        """Initialize the chat handler.
        
        Args:
            llm_client: An instance of OpenAIClient for LLM interactions
            mcp_server: An instance of MCPCalendarServer for tool execution
        """
        self.llm_client = llm_client
        self.mcp_server = mcp_server
        self.conversation_history: List[Dict[str, str]] = []
    
    def _get_system_prompt(self) -> str:
        """Return the system prompt for the chat assistant."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        current_year = datetime.now().year
        
        return f"""You are a helpful calendar assistant. Your job is to help users manage their Google Calendar.

Current date and time: {current_time}
Current year: {current_year}

When users want to add events, extract the following information:
- Event title/name
- Date (convert to YYYY-MM-DD format)
- Start time (convert to 24-hour HH:MM format)
- End time (if mentioned, otherwise assume 1 hour duration)
- Location (if mentioned)
- Description/notes (if mentioned)

Date format notes:
- If user says "03/12", interpret based on context. In Hong Kong/Asia, this typically means December 3rd.
- If user says "tomorrow", "next Monday", etc., calculate the actual date.
- Always use the current year unless specified otherwise.

Time format notes:
- Convert times like "2pm" to "14:00"
- Convert times like "9:30am" to "09:30"

Location abbreviations:
- "SHB" = Shaw Building
- Common building abbreviations should be expanded for clarity.

Always confirm the event details with the user before creating it, unless they explicitly ask you to create it directly.
After successfully creating an event, provide a summary of what was created.

You can also:
- List upcoming events to check schedule
- Update existing events
- Delete events

Be concise and helpful in your responses."""
    
    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []
    
    async def chat(self, user_message: str) -> Dict[str, Any]:
        """Process a user message and return a response.
        
        This method handles the full chat flow including tool calling.
        
        Args:
            user_message: The user's input message
            
        Returns:
            A dictionary containing the assistant's response and any tool results
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": self._get_system_prompt()}
        ] + self.conversation_history
        
        # Get tools
        tools = self.mcp_server.get_tools()
        
        try:
            # Call LLM with tools
            response = self._call_llm_with_tools(messages, tools)
            
            # Check if we need to execute tools
            if response.get("tool_calls"):
                tool_results = []
                for tool_call in response["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])
                    
                    # Execute the tool
                    result = self.mcp_server.execute_tool(tool_name, arguments)
                    tool_results.append({
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result": result
                    })
                
                # Add assistant message with tool calls
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.get("content", ""),
                    "tool_calls": response["tool_calls"]
                })
                
                # Add tool results to conversation
                for i, tool_result in enumerate(tool_results):
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": response["tool_calls"][i].get("id", f"call_{i}"),
                        "content": json.dumps(tool_result["result"])
                    })
                
                # Get final response from LLM
                final_messages = [
                    {"role": "system", "content": self._get_system_prompt()}
                ] + self.conversation_history
                
                final_response = self._call_llm_with_tools(final_messages, tools)
                
                assistant_message = final_response.get("content", "I've processed your request.")
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                
                return {
                    "message": assistant_message,
                    "tool_calls": tool_results,
                    "success": True
                }
            else:
                # No tool calls, just return the response
                assistant_message = response.get("content", "I'm not sure how to help with that.")
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                
                return {
                    "message": assistant_message,
                    "tool_calls": [],
                    "success": True
                }
                
        except Exception as e:
            logger.exception(f"Error in chat: {e}")
            error_message = f"Sorry, I encountered an error: {str(e)}"
            return {
                "message": error_message,
                "tool_calls": [],
                "success": False,
                "error": str(e)
            }
    
    def _call_llm_with_tools(self, messages: List[Dict], tools: List[Dict]) -> Dict[str, Any]:
        """Call the LLM with tool definitions.
        
        Args:
            messages: The conversation messages
            tools: The available tools
            
        Returns:
            The LLM response including any tool calls
        """
        if not self.llm_client._is_ready():
            # Stub response for testing without API key
            return self._generate_stub_response(messages[-1].get("content", ""))
        
        try:
            # Use the OpenAI client to make the call with tools
            response = self.llm_client._chat_completion_with_tools(
                messages=messages,
                tools=tools,
                temperature=0.7,
                max_tokens=1024
            )
            return response
        except Exception as e:
            logger.exception(f"LLM call failed: {e}")
            raise
    
    def _generate_stub_response(self, user_message: str) -> Dict[str, Any]:
        """Generate a stub response for testing without API key.
        
        This parses the user message and generates appropriate tool calls.
        """
        user_lower = user_message.lower()
        
        # Check for event creation intent
        if any(word in user_lower for word in ["meeting", "schedule", "add", "create", "book"]):
            # Extract date - look for patterns like "03/12", "march 12", etc.
            date = None
            date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})', user_message)
            if date_match:
                day, month = date_match.groups()
                year = datetime.now().year
                # In HK format, DD/MM
                date = f"{year}-{int(month):02d}-{int(day):02d}"
            
            # Extract time - look for patterns like "2pm", "14:00", etc.
            time = None
            time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', user_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = time_match.group(2) or "00"
                ampm = time_match.group(3)
                if ampm == "pm" and hour < 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0
                time = f"{hour:02d}:{minute}"
            
            # Extract location
            location = ""
            if "shb" in user_lower:
                location = "Shaw Building"
            elif "zoom" in user_lower:
                location = "Zoom"
            
            # Default values if not found
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
            if not time:
                time = "14:00"
            
            return {
                "content": "",
                "tool_calls": [{
                    "id": "stub_call_1",
                    "type": "function",
                    "function": {
                        "name": "add_calendar_event",
                        "arguments": json.dumps({
                            "title": "Meeting",
                            "date": date,
                            "start_time": time,
                            "location": location
                        })
                    }
                }]
            }
        
        # Check for list events intent
        elif any(word in user_lower for word in ["list", "show", "what", "schedule", "upcoming"]):
            return {
                "content": "",
                "tool_calls": [{
                    "id": "stub_call_1",
                    "type": "function",
                    "function": {
                        "name": "list_calendar_events",
                        "arguments": json.dumps({"days_ahead": 7})
                    }
                }]
            }
        
        # Default response
        return {
            "content": "I can help you manage your calendar. You can ask me to:\n- Add events (e.g., 'Schedule a meeting on 03/12 at 2pm in SHB')\n- List upcoming events\n- Update or delete events\n\nWhat would you like to do?",
            "tool_calls": []
        }
