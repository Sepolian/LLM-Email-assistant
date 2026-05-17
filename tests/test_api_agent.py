import importlib

from fastapi.testclient import TestClient

from conftest import FakeGmailClient, FakeGCalClient, FakeLLMClient
from llm_email_app.agent.graph import AgentRuntime
from llm_email_app.email.rules import ProcessedEmailStore


def _load_api(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_APPROVALS_PATH", str(tmp_path / "agent_approvals.json"))
    monkeypatch.setenv("AGENT_WORK_ITEMS_PATH", str(tmp_path / "agent_work_items.json"))
    monkeypatch.setenv("AGENT_THREADS_PATH", str(tmp_path / "agent_threads.json"))
    monkeypatch.setenv("AGENT_TIMELINE_PATH", str(tmp_path / "agent_timeline.json"))
    monkeypatch.setenv("AGENT_RUNS_PATH", str(tmp_path / "agent_runs.json"))
    monkeypatch.setenv("AGENT_CHECKPOINTS_PATH", str(tmp_path / "agent_checkpoints.sqlite"))
    monkeypatch.setenv("AGENT_MEMORY_DIR", str(tmp_path / "memory"))
    config = importlib.import_module("llm_email_app.config")
    importlib.reload(config)
    importlib.reload(importlib.import_module("llm_email_app.llm.openai_client"))
    importlib.reload(importlib.import_module("llm_email_app.agent.graph"))
    return importlib.reload(importlib.import_module("llm_email_app.api"))


def test_chat_and_approval_endpoints_use_agent_runtime(monkeypatch, tmp_path):
    api = _load_api(monkeypatch, tmp_path)
    runtime = AgentRuntime(
        checkpoint_path=tmp_path / "chat.sqlite",
        approvals_path=tmp_path / "chat_approvals.json",
        runs_path=tmp_path / "chat_runs.json",
        memory_dir=tmp_path / "chat_memory",
        llm_client=FakeLLMClient(),
    )
    fake_gmail = FakeGmailClient()
    fake_gcal = FakeGCalClient()

    monkeypatch.setattr(api, "AGENT_RUNTIME", runtime)
    monkeypatch.setattr(api, "get_credentials", lambda request: {"token": "fake"})
    monkeypatch.setattr(api, "load_persisted_credentials", lambda: None)
    monkeypatch.setattr(api, "_append_automation_log", lambda message, level="info": None)
    monkeypatch.setattr(
        api,
        "_load_automation_settings",
        lambda: {
            "auto_add_events": False,
            "agent_enabled": True,
            "agent_mode": "semi_auto",
            "agent_shadow_mode": False,
        },
    )
    monkeypatch.setattr(api.RULE_MANAGER, "get_state", lambda: {"automation_enabled": False, "rules": []})

    api.app.dependency_overrides[api.get_gmail_client] = lambda: fake_gmail
    api.app.dependency_overrides[api.get_gcal_client] = lambda: fake_gcal

    try:
        with TestClient(api.app) as client:
            chat_response = client.post("/chat", json={"message": "schedule a meeting tomorrow at 2pm about roadmap"})
            assert chat_response.status_code == 200
            chat_payload = chat_response.json()
            assert chat_payload["pending_approval"] is True

            approvals_response = client.get("/agent/approvals?status=pending")
            assert approvals_response.status_code == 200
            approvals = approvals_response.json()["approvals"]
            assert len(approvals) == 1

            approve_response = client.post(f"/agent/approvals/{approvals[0]['id']}/approve")
            assert approve_response.status_code == 200
            assert fake_gcal.created
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_automation_run_endpoint_uses_agentic_triage(monkeypatch, tmp_path):
    api = _load_api(monkeypatch, tmp_path)
    llm_client = FakeLLMClient(
        summary="Budget sync next Tuesday at 10am.",
        proposals=[
            {
                "title": "Budget Sync",
                "start": "2026-05-12T10:00:00+08:00",
                "end": "2026-05-12T11:00:00+08:00",
                "attendees": [],
                "location": "Zoom",
                "notes": "Review the budget.",
            }
        ],
        matches=[],
    )
    runtime = AgentRuntime(
        checkpoint_path=tmp_path / "automation.sqlite",
        approvals_path=tmp_path / "automation_approvals.json",
        runs_path=tmp_path / "automation_runs.json",
        memory_dir=tmp_path / "automation_memory",
        llm_client=llm_client,
    )
    fake_gmail = FakeGmailClient()
    fake_gcal = FakeGCalClient()
    queued = []

    def fake_add_proposal(proposal, email_id, email_subject, email_summary):
        entry = {
            "id": f"proposal-{len(queued) + 1}",
            "title": proposal["title"],
            "email_id": email_id,
            "email_subject": email_subject,
            "email_summary": email_summary,
        }
        queued.append(entry)
        return entry

    monkeypatch.setattr(api, "AGENT_RUNTIME", runtime)
    monkeypatch.setattr(api, "AGENT_PROCESSED_STORE", ProcessedEmailStore(tmp_path / "processed.json"))
    monkeypatch.setattr(api, "_add_proposal", fake_add_proposal)
    monkeypatch.setattr(api, "get_credentials", lambda request: {"token": "fake"})
    monkeypatch.setattr(api, "load_persisted_credentials", lambda: None)
    monkeypatch.setattr(api, "_append_automation_log", lambda message, level="info": None)
    monkeypatch.setattr(api, "_load_cached_recent_emails", lambda lookback_days, limit: [fake_gmail.messages["email-1"]])
    monkeypatch.setattr(
        api,
        "_load_automation_settings",
        lambda: {
            "auto_add_events": False,
            "agent_enabled": True,
            "agent_mode": "auto",
            "agent_shadow_mode": False,
        },
    )
    monkeypatch.setattr(api.RULE_MANAGER, "get_state", lambda: {"automation_enabled": False, "rules": []})

    api.app.dependency_overrides[api.get_gmail_client] = lambda: fake_gmail
    api.app.dependency_overrides[api.get_gcal_client] = lambda: fake_gcal

    try:
        with TestClient(api.app) as client:
            response = client.post("/automation/run")
            assert response.status_code == 200
            status_payload = response.json()
            assert "last_run_at" in status_payload
            assert queued and queued[0]["title"] == "Budget Sync"
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()
