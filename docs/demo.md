# Demo Mode

## Purpose

Demo mode provides a fast local showcase without Google OAuth. It uses committed fixture templates and generates fresh mailbox and calendar state at startup or reset time.

## Demo assets

- `src/llm_email_app/demo_fixtures/mailbox.json`
- `src/llm_email_app/demo_fixtures/calendar.json`
- `src/llm_email_app/demo_data.py`

The fixture files are templates. The generated runtime state is written to:

- `tmp/demo_mailbox_state.json`
- `tmp/demo_calendar_state.json`

## Time handling

Demo dates are not hard-coded to one past week. `reset_demo_world()` rebuilds mailbox and calendar data relative to:

1. `DEMO_REFERENCE_TIME`, if set
2. otherwise, the server's current local time

The official scenarios stay within the next 14 days from that reference time.

## Official demo scripts

`demo_data.py` defines three built-in scripts:

- `flagship_conflict`: resolve a meeting request that conflicts with an existing event
- `show_schedule`: inspect the next 7 days of calendar events
- `search_and_summarize`: find a budget-related email and summarize it

The flagship script demonstrates the full interaction loop:

1. start a thread
2. inspect mailbox and calendar context
3. detect a conflict
4. create a blocking work item
5. wait for user input
6. resume the same thread
7. produce a draft and final timeline

## Running the demo

Set these variables in `.env`:

```env
DRY_RUN=true
DEMO_MODE=true
AGENT_ENABLED=true
OPENAI_API_KEY=...
OPENAI_API_BASE=http://your-openai-compatible-endpoint
OPENAI_MODEL=your-model
```

Optional:

```env
DEMO_REFERENCE_TIME=2026-05-17T09:00:00+08:00
```

Then start the app and open `http://localhost:8000`.

## Reset behavior

- backend startup in demo mode resets mailbox, calendar, and assistant runtime state
- `POST /agent/demo/start` also resets the demo world before launching an official script
- `POST /agent/demo/reset` clears runtime state, and `scope=full` rebuilds mailbox and calendar data

## Notes

- Demo mode uses the same API surface as live mode.
- Draft creation, calendar writes, labels, and message mutations persist inside the local demo state files until the next reset.
