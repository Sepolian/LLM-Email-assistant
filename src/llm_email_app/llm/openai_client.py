"""OpenAI client wrapper.

This module implements a small `OpenAIClient` that will:
- Use the official `openai` Python package when `OPENAI_API_KEY` is set.
- Fall back to a safe, deterministic stub response when no API key is available (so local dev and tests don't call the network).

Behaviour contract (simple):
- summarize_email(email_body: str, email_sender: Optional[str] = None, ...) -> dict with keys:
  - text: short human-readable summary
  - proposals: list of events {title, start (ISO), end (ISO), attendees, location, notes}

The wrapper tries to parse JSON returned by the model. The prompt asks the model to reply with JSON only.
"""
from typing import Dict, Any, Optional, List, Tuple
import os
import json
import re
import requests
from datetime import datetime, timezone
import logging

from llm_email_app.config import settings


def _extract_json(text: str) -> Optional[dict]:
    """Try to extract the first JSON object from a model response.

    Returns parsed dict or None on failure.
    """
    # common pattern: model may wrap JSON in ``` or plain text. Find first { ... }
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        # try to fix common trailing commas by a simple heuristic
        try:
            fixed = re.sub(r",\s*,+", ",", candidate)
            return json.loads(fixed)
        except Exception:
            return None

logger = logging.getLogger(__name__)


class OpenAIClient:
    def __init__(self, api_key: str = None, model: Optional[str] = None, api_base: Optional[str] = None):
        """Create client.

        Configuration is read from parameters or environment via `settings`.

        - `api_key`: API key for the OpenAI-format API (from settings.OPENAI_API_KEY)
        - `model`: model id/name (from OPENAI_MODEL)
        - `api_base`: base URL for the API (from OPENAI_API_BASE). If provided, the client will
          send HTTP requests with `requests` to this endpoint instead of using the `openai` SDK.

        This avoids hard-coding model names or provider URLs in code; they should be provided
        by environment variables at deploy time.
        """
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or os.getenv("OPENAI_MODEL")
        # allow alternative env var names for base URL
        self.api_base = api_base or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_API_URL")

        # prefer explicit base URL: if set, use requests to call an OpenAI-compatible endpoint
        self._use_requests = bool(self.api_base)
        self._client = None

        if not self._use_requests and self.api_key:
            # try to use official openai SDK if available and no custom base provided
            try:
                import openai

                openai.api_key = self.api_key
                self._client = openai
            except Exception:
                # SDK not available; fall back to requests if api_base provided, else to stub
                self._client = None

    def _is_ready(self) -> bool:
        return bool(self._client or self._use_requests)

    def _chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        context_tag: str,
    ) -> Tuple[str, Any]:
        if not self.model:
            raise RuntimeError('Model id must be provided via OPENAI_MODEL or constructor argument')
        if self._use_requests:
            if not self.api_key or not self.model:
                raise RuntimeError('API key and model are required when OPENAI_API_BASE is set')
            url = self.api_base.rstrip('/') + '/v1/chat/completions'
            headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
            payload = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            resp = r.json()
            logger.info('=== Full Raw LLM Response (%s, requests) ===', context_tag)
            logger.info(json.dumps(resp, indent=2, ensure_ascii=False))
            choices = resp.get('choices', [])
            text = ''
            if choices:
                first = choices[0]
                if isinstance(first, dict):
                    text = first.get('message', {}).get('content', '') or first.get('text', '')
            logger.info('=== Extracted Text Content (%s) ===', context_tag)
            logger.info(text)
            return text, resp

        if not self._client:
            raise RuntimeError('OpenAI client not configured')

        resp = self._client.ChatCompletion.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        logger.info('=== Full Raw LLM Response (%s, SDK) ===', context_tag)
        if isinstance(resp, dict):
            logger.info(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            try:
                resp_dict = {
                    'id': getattr(resp, 'id', None),
                    'object': getattr(resp, 'object', None),
                    'created': getattr(resp, 'created', None),
                    'model': getattr(resp, 'model', None),
                    'choices': [
                        {
                            'index': getattr(choice, 'index', None),
                            'message': {
                                'role': getattr(getattr(choice, 'message', None), 'role', None),
                                'content': getattr(getattr(choice, 'message', None), 'content', None),
                            } if hasattr(choice, 'message') else None,
                            'finish_reason': getattr(choice, 'finish_reason', None),
                        }
                        for choice in (getattr(resp, 'choices', []) or [])
                    ],
                }
                logger.info(json.dumps(resp_dict, indent=2, ensure_ascii=False))
            except Exception as exc:
                logger.info('Raw response (object): %s', resp)
                logger.info('Could not convert to dict: %s', exc)

        text = ''
        choices = resp.get('choices') if isinstance(resp, dict) else getattr(resp, 'choices', None)
        if choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get('message', {}).get('content', '') or first.get('text', '')
            else:
                msg = getattr(first, 'message', None)
                text = msg.get('content') if isinstance(msg, dict) else getattr(msg, 'content', '')
                if not text:
                    text = getattr(first, 'text', '')

        logger.info('=== Extracted Text Content (%s) ===', context_tag)
        logger.info(text)
        return text, resp

    def summarize_email(self, email_body: str, email_received_time: Optional[str] = None, current_time: Optional[str] = None, email_sender: Optional[str] = None, temperature: float = 0.0, max_tokens: int = settings.MAX_TOKEN, return_raw_response: bool = False) -> Dict[str, Any]:
        """Summarize an email and propose calendar events.

        If no OpenAI key / client present, returns a deterministic stub useful for local development and tests.
        """
        # Use max_tokens from settings if not provided
        if max_tokens is None:
            max_tokens = settings.MAX_TOKEN
        
        # If neither requests-based nor SDK client is configured, fall back to stub
        if not self._is_ready():
            # deterministic fallback used in tests and local dev
            return {
                "text": "Stub summary: This email proposes a meeting next week to discuss the Q4 roadmap.",
                "proposals": [
                    {
                        "title": "Q4 roadmap sync",
                        "start": "2025-11-24T10:00:00",
                        "end": "2025-11-24T11:00:00",
                        "attendees": [],
                        "location": "Zoom",
                        "notes": "Auto-generated by LLM"
                    }
                ],
            }

        # ensure current_time is populated for prompts
        if not current_time:
            current_time = datetime.now(timezone.utc).isoformat()

        system_prompt = (
            "You are a helpful assistant that extracts scheduling information from a user's email. "
            "Given the full email body and the sender, produce a short, clean, human-readable summary (include the sender's name if available), you should also translate the email content into English if it's not in English. "
            "It is recommened to use as less words as possible to describe the email content. Never use more than 1 line to describe the email content. "
            "You should consider the sender's context when summarizing the email and propose events accordingly. If it is a subscription or promotional email, you should report the true key information only. "
            "an array of proposed events. Respond with JSON only (no extra explanation).\n\n"
            "IMPORTANT: All proposed event datetimes must be expressed in Hong Kong local time (Asia/Hong_Kong, UTC+08:00). "
            "Use full ISO 8601 timestamps with timezone offset +08:00, e.g. 2025-11-24T10:00:00+08:00."
            "DATE FORMAT RECOGNITION: When parsing dates from the email body, you must be aware of different date formats based on location:\n"
            "- For locations in Europe, Asia (including Hong Kong, UK, Australia, etc.): Use DD/MM format (day/month)\n"
            "- For locations in North America (US, Canada): Use MM/DD format (month/day)\n"
            "- Infer the location from the sender's email domain, email content, or location mentioned in the email\n"
            "- If the date format is ambiguous (e.g., 01/02 could be Jan 2 or Feb 1), use context clues like:\n"
            "  * Sender's email domain (.com, .uk, .au, .hk, etc.)\n"
            " * Location mentioned in the email\n"
            " * Language and cultural context\n"
            "- When in doubt or no location is specified, default to DD/MM format"
        )

        # include received/current time context to help the model propose sensible event datetimes
        time_context = ""
        if email_received_time:
            time_context += f"Email received at: {email_received_time}. "
        time_context += f"Current system time: {current_time}. "
        
        # include sender information if available
        sender_context = ""
        if email_sender:
            sender_context = f"Email sender: {email_sender}. "

        user_prompt = (
            "Email:\n" + email_body + "\n\n"
            + sender_context
            + time_context
            + "\nProduce a JSON object with keys:\n"
            "- text: brief summary string\n"
            "- proposals: an array (possibly empty) of objects with fields: title, start (ISO 8601), end (ISO 8601), attendees (array of emails), location, notes.\n"
            "If there are no scheduling intents, use an empty array for proposals. Return JSON only.\n\n"
            "IMPORTANT: Regardless of the timezone of any provided timestamps, return all proposal start/end datetimes in Hong Kong local time (Asia/Hong_Kong, UTC+08:00) using ISO 8601 with +08:00 offset."
             "When parsing dates, consider the sender's location and use the appropriate date format (DD/MM for default or unspecified location, MM/DD for US/Canada)."
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        try:
            text, raw_response = self._chat_completion(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                context_tag='summarize',
            )

            parsed = _extract_json(text)
            result = parsed if parsed is not None else {"text": text.strip(), "proposals": []}
            
            # Include raw response in result if requested
            if return_raw_response:
                result["_raw_response"] = raw_response
                result["_raw_text"] = text
            
            return result

        except Exception as e:
            # On API error, raise to let caller decide; include message for debugging
            raise RuntimeError(f"OpenAI-format API call failed: {e}")
    