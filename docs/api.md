# API Overview

## Authentication and session

- `GET /login`
- `GET /auth/callback`
- `GET /logout`
- `GET /user`

In demo mode, `/user` returns the local demo profile and no Google login is required.

## Email and calendar

- `GET /emails`
- `GET /emails/cache`
- `GET /emails/search`
- `POST /emails/drafts`
- `POST /emails/{message_id}/read`
- `POST /emails/{message_id}/archive`
- `DELETE /emails/{message_id}`

- `GET /calendar/events`
- `GET /calendar/cache`
- `POST /calendar/events`
- `PUT /calendar/events/{event_id}`
- `DELETE /calendar/events/{event_id}`

These routes talk to live provider clients when OAuth credentials are present, or to local demo state when `DEMO_MODE=true`.

## Chat and assistant runtime

- `POST /chat`
- `POST /chat/reset`
- `GET /chat/tools`

- `GET /agent/threads`
- `GET /agent/threads/{thread_id}`
- `GET /agent/threads/{thread_id}/timeline`
- `POST /agent/threads/{thread_id}/continue`

- `GET /agent/work-items`
- `GET /agent/work-items/{work_item_id}`
- `POST /agent/work-items/{work_item_id}/respond`

- `POST /agent/demo/start`
- `POST /agent/demo/reset`

The chat page uses these thread and work-item endpoints as the main assistant workflow surface.

## Automation and settings

- `GET /automation/status`
- `GET /automation/logs`
- `GET /automation/rules`
- `POST /automation/rules`
- `DELETE /automation/rules/{rule_id}`
- `PUT /automation/settings`
- `GET /automation/extra-settings`
- `PUT /automation/extra-settings`
- `POST /automation/run`

## Compatibility routes

The backend still contains proposal and approval routes used by older flows:

- `/proposals`
- `/agent/approvals`

They remain available, but the current chat-led demo relies on threads, timelines, and work items.
