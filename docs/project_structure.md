# Project structure

- `README.md` - top-level overview and combined setup guide
- `requirements.txt` - Python backend dependencies
- `docs/` - additional notes (`project_structure.md`, `todo.md`)
- `frontend/` - React single-page app
  - `index.html` - root document served to the browser
  - `app.jsx` - SPA bootstrap and router
  - `pages/` - routed views (`Home.jsx`, `Email.jsx`, `Calendar.jsx`, `Settings.jsx`)
- `src/llm_email_app/` - backend Python package
  - `config.py` - environment-driven configuration
  - `main.py` - entry point for the FastAPI app
  - `api.py` - FastAPI route definitions
  - `auth/` - Google OAuth helpers (`google_oauth.py`, `session.py`)
  - `email/` - Gmail integration (`gmail_client.py` and helpers)
  - `calendar/` - Google Calendar client (`gcal.py`)
  - `llm/` - LLM adapters (`openai_client.py`)
- `tests/` - pytest-based smoke and integration tests (`test_smoke.py`)
- `tokens/` - runtime token cache (`google_token.json`)

Next steps (implementation order):
3. Implement OpenAI client and mapping of extracted data to calendar event models.
4. Implement Gmail OAuth and message fetching (with proper parsing for body and attachments).
5. Implement Google Calendar event creation and user confirmation UI/flow.
6. Add tests and CI steps; secure token storage.
7. Add user-defined tagging rules and LLM-driven tagging:
  - **Rule engine:** Add `src/llm_email_app/email/rules.py` which implements a `RuleManager` to persist user rules (JSON at `data/rules.json`), evaluate messages, and orchestrate actions.
  - **Gmail label helpers:** Extend `src/llm_email_app/email/gmail_client.py` with `check_or_create_label(label_name)` and `apply_labels_to_message(message_id, label_ids)` to encapsulate label operations.
  - **LLM-driven tagging:** The LLM will be given additional instructions in the system prompt to recommend tags/labels. The system prompt must include the rule specification and require the model to output a strict JSON response. Because some messages may prevent reading the full body, prompts and rules must explicitly include the message `subject` and sender `from` address as primary judging criteria. Example response schema (must be JSON-only):

```
{
  "labels": ["Follow Up", "Invoice"],
  "reasons": ["subject contains 'invoice'", "from matches billing@"],
  "actions": [{"type": "add_label", "label": "Follow Up"}]
}
```

  - **Integration point:** After fetching and parsing a message, the app calls the LLM with the system prompt requesting tags. The app then validates the JSON response, ensures labels exist via `GmailClient.check_or_create_label`, and applies them with `apply_labels_to_message`.
  - **Testing:** Mock the LLM responses during tests and unit-test the parser and label application logic.


