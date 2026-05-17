from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

def _seed_paths(tmp_path: Path) -> tuple[Path, Path]:
    fixture_dir = Path(__file__).resolve().parents[1] / "src" / "llm_email_app" / "demo_fixtures"
    mailbox_seed = tmp_path / "mailbox_seed.json"
    calendar_seed = tmp_path / "calendar_seed.json"
    mailbox_seed.write_text((fixture_dir / "mailbox.json").read_text(encoding="utf-8"), encoding="utf-8")
    calendar_seed.write_text((fixture_dir / "calendar.json").read_text(encoding="utf-8"), encoding="utf-8")
    return mailbox_seed, calendar_seed


def _reload_demo_modules(monkeypatch, tmp_path: Path):
    mailbox_seed, calendar_seed = _seed_paths(tmp_path)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("DEMO_REFERENCE_TIME", "2026-05-05T09:00:00+08:00")
    monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setenv("AUTO_LABEL_REQUEST_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("DEMO_EMAIL_FIXTURE_PATH", str(mailbox_seed))
    monkeypatch.setenv("DEMO_CALENDAR_FIXTURE_PATH", str(calendar_seed))
    monkeypatch.setenv("DEMO_EMAIL_STATE_PATH", str(tmp_path / "mailbox_state.json"))
    monkeypatch.setenv("DEMO_CALENDAR_STATE_PATH", str(tmp_path / "calendar_state.json"))
    monkeypatch.setenv("AUTO_LABEL_RULES_PATH", str(tmp_path / "rules.json"))
    monkeypatch.setenv("AUTO_LABEL_PROCESSED_PATH", str(tmp_path / "auto_label_processed.json"))
    monkeypatch.setenv("AGENT_PROCESSED_PATH", str(tmp_path / "agent_processed.json"))
    monkeypatch.setenv("AGENT_APPROVALS_PATH", str(tmp_path / "agent_approvals.json"))
    monkeypatch.setenv("AGENT_WORK_ITEMS_PATH", str(tmp_path / "agent_work_items.json"))
    monkeypatch.setenv("AGENT_THREADS_PATH", str(tmp_path / "agent_threads.json"))
    monkeypatch.setenv("AGENT_TIMELINE_PATH", str(tmp_path / "agent_timeline.json"))
    monkeypatch.setenv("AGENT_RUNS_PATH", str(tmp_path / "agent_runs.json"))
    monkeypatch.setenv("AGENT_CHECKPOINTS_PATH", str(tmp_path / "agent_checkpoints.sqlite"))
    monkeypatch.setenv("AGENT_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_URL", raising=False)

    config = importlib.import_module("llm_email_app.config")
    importlib.reload(config)
    demo_data = importlib.reload(importlib.import_module("llm_email_app.demo_data"))
    openai_client_module = importlib.reload(importlib.import_module("llm_email_app.llm.openai_client"))
    gmail_client_module = importlib.reload(importlib.import_module("llm_email_app.email.gmail_client"))
    gcal_module = importlib.reload(importlib.import_module("llm_email_app.calendar.gcal"))
    graph_module = importlib.reload(importlib.import_module("llm_email_app.agent.graph"))
    session_module = importlib.reload(importlib.import_module("llm_email_app.auth.session"))
    api = importlib.reload(importlib.import_module("llm_email_app.api"))

    return api


def test_demo_mode_user_and_mailbox_endpoints(monkeypatch, tmp_path):
    demo_api = _reload_demo_modules(monkeypatch, tmp_path)

    with TestClient(demo_api.app) as client:
        user_resp = client.get("/user")
        assert user_resp.status_code == 200
        user_payload = user_resp.json()
        assert user_payload["demo_mode"] is True
        assert user_payload["email"] == "avery.chen@demo.mailflow.local"

        email_resp = client.get("/emails?folder=inbox&page=1&per_page=20&days=14")
        assert email_resp.status_code == 200
        mailbox = email_resp.json()
        inbox = mailbox["folders"]["inbox"]["items"]
        assert len(inbox) >= 4
        launch_email = next(item for item in inbox if item["id"] == "demo-inbox-client-launch")
        assert launch_email["subject"].startswith("Need confirmation: client launch rehearsal")

        calendar_resp = client.get("/calendar/events?max_results=50")
        assert calendar_resp.status_code == 200
        events = calendar_resp.json()
        conflict_event = next(event for event in events if event["summary"] == "Exec briefing")
        conflict_start = datetime.fromisoformat(conflict_event["start"]["dateTime"])
        assert "2026-05-08" in launch_email["subject"]
        assert "15:00" in launch_email["subject"]
        assert conflict_start.date().isoformat() == "2026-05-08"
        assert conflict_start.hour == 15
        assert conflict_start <= datetime.fromisoformat("2026-05-19T09:00:00+08:00")


def test_demo_mode_mailbox_mutations_persist(monkeypatch, tmp_path):
    demo_api = _reload_demo_modules(monkeypatch, tmp_path)

    with TestClient(demo_api.app) as client:
        draft_resp = client.post(
            "/emails/drafts",
            json={
                "to": "maya@northstarstudios.co",
                "subject": "Re: client launch rehearsal",
                "body": "Confirmed. I can join.",
                "reply_to_message_id": "demo-inbox-client-launch",
            },
        )
        assert draft_resp.status_code == 200

        label_resp = client.post("/automation/rules", json={"label": "VIP", "reason": "emails from Maya Patel"})
        assert label_resp.status_code == 200

        apply_label_resp = client.post("/emails/demo-inbox-client-launch/read?read=true")
        assert apply_label_resp.status_code == 200

        demo_client = demo_api.get_gmail_client(None)
        assert demo_client.apply_labels_to_message("demo-inbox-client-launch", ["VIP"]) is True

        delete_resp = client.delete("/emails/demo-inbox-travel")
        assert delete_resp.status_code == 200

        mailbox_resp = client.get("/emails?folder=drafts&page=1&per_page=20&days=30")
        drafts = mailbox_resp.json()["folders"]["drafts"]["items"]
        assert any(item["subject"] == "Re: client launch rehearsal" for item in drafts)

        trash_resp = client.get("/emails?folder=trash&page=1&per_page=20&days=30")
        trash_items = trash_resp.json()["folders"]["trash"]["items"]
        assert any(item["id"] == "demo-inbox-travel" for item in trash_items)

        inbox_resp = client.get("/emails?folder=inbox&page=1&per_page=20&days=30")
        inbox_items = inbox_resp.json()["folders"]["inbox"]["items"]
        launch_email = next(item for item in inbox_items if item["id"] == "demo-inbox-client-launch")
        assert "VIP" in launch_email["labels"]


def test_demo_mode_proposal_accept_creates_local_calendar_event(monkeypatch, tmp_path):
    demo_api = _reload_demo_modules(monkeypatch, tmp_path)

    proposals_payload = {
        "generated_at": "2026-05-06T00:00:00+08:00",
        "retention_days": 30,
        "count": 1,
        "proposals": [
            {
                "id": "proposal-demo-1",
                "created_at": "2026-05-06T09:00:00+08:00",
                "status": "pending",
                "email_id": "demo-inbox-budget",
                "email_subject": "Budget review follow-up and requested reply",
                "email_summary": "Budget review next Tuesday at 10:00.",
                "title": "Budget review",
                "start": "2026-05-12T10:00:00+08:00",
                "end": "2026-05-12T11:00:00+08:00",
                "location": "Zoom",
                "attendees": [],
                "notes": "Review numbers before sign-off."
            }
        ],
    }
    demo_api.PROPOSALS_CACHE_PATH.write_text(json.dumps(proposals_payload), encoding="utf-8")

    with TestClient(demo_api.app) as client:
        accept_resp = client.post("/proposals/proposal-demo-1/accept")
        assert accept_resp.status_code == 200
        accepted = accept_resp.json()
        assert accepted["success"] is True
        assert accepted["demo_mode"] is True

        events_resp = client.get("/calendar/events?max_results=100")
        events = events_resp.json()
        assert any(event["summary"] == "Budget review" for event in events)
