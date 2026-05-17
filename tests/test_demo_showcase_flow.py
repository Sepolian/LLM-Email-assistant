import importlib

from fastapi.testclient import TestClient

from conftest import FakeGCalClient, FakeGmailClient, FakeLLMClient, make_context


def _seed_conflict(fake_gcal: FakeGCalClient) -> None:
    fake_gcal.events = [
        {
            "id": "demo-event-client-rehearsal-conflict",
            "summary": "Exec briefing",
            "start": {"dateTime": "2026-05-08T15:00:00+08:00"},
            "end": {"dateTime": "2026-05-08T15:45:00+08:00"},
            "location": "Board room",
        }
    ]


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


def test_flagship_demo_creates_conflict_work_item_and_timeline(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()
    _seed_conflict(fake_gcal)

    result = runtime.start_demo(
        script_id="flagship_conflict",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        mode="semi_auto",
    )

    assert result["pending_work_item"] is True
    work_item = runtime.get_work_item(result["work_item_id"])
    assert work_item is not None
    assert work_item["type"] == "conflict_decision"
    assert work_item["allowed_actions"] == ["choose"]
    assert work_item["allowed_responses"] == ["keep_existing", "accept_new", "suggest_only"]

    thread = runtime.get_thread(result["thread_id"])
    assert thread is not None
    assert thread["status"] == "needs_input"

    timeline_types = [item["type"] for item in runtime.get_timeline(result["thread_id"])]
    assert "task_understood" in timeline_types
    assert "tool_started" in timeline_types
    assert "needs_input" in timeline_types


def test_flagship_demo_resume_to_draft_review_and_complete(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()
    _seed_conflict(fake_gcal)

    started = runtime.start_demo(
        script_id="flagship_conflict",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        mode="semi_auto",
    )
    thread_id = started["thread_id"]

    choose_result = runtime.resume_work_item(
        work_item_id=started["work_item_id"],
        action="choose",
        context=make_context(
            runtime=runtime,
            thread_id=thread_id,
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
            source="demo",
        ),
        payload={"choice": "accept_new"},
    )

    assert choose_result["pending_work_item"] is True
    draft_review = runtime.get_work_item(choose_result["work_item_id"])
    assert draft_review is not None
    assert draft_review["type"] == "draft_review"
    assert fake_gcal.deleted == ["demo-event-client-rehearsal-conflict"]

    final_result = runtime.resume_work_item(
        work_item_id=choose_result["work_item_id"],
        action="approve",
        context=make_context(
            runtime=runtime,
            thread_id=thread_id,
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
            source="demo",
        ),
        payload={},
    )

    assert final_result["success"] is True
    assert not final_result.get("pending_work_item")
    assert len(fake_gmail.created_drafts) == 1
    assert fake_gmail.created_drafts[0]["subject"].startswith("Re:")
    assert runtime.get_thread(thread_id)["status"] == "completed"
    timeline_types = [item["type"] for item in runtime.get_timeline(thread_id)]
    assert "resumed" in timeline_types
    assert timeline_types[-1] == "completed"


def test_continue_from_here_creates_new_free_thread(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()
    _seed_conflict(fake_gcal)
    runtime.start_demo(
        script_id="show_schedule",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        mode="semi_auto",
    )

    branch = runtime.continue_from_thread("demo-show-schedule")

    assert branch["thread_kind"] == "free"
    assert branch["branch_source_thread_id"] == "demo-show-schedule"
    assert branch["thread_id"] != "demo-show-schedule"
    assert runtime.get_timeline(branch["thread_id"])


def test_work_item_api_demo_flow(monkeypatch, tmp_path):
    api = _load_api(monkeypatch, tmp_path)
    runtime = api.AgentRuntime(
        checkpoint_path=tmp_path / "demo.sqlite",
        approvals_path=tmp_path / "approvals.json",
        work_items_path=tmp_path / "work_items.json",
        threads_path=tmp_path / "threads.json",
        timeline_path=tmp_path / "timeline.json",
        runs_path=tmp_path / "runs.json",
        memory_dir=tmp_path / "memory",
        llm_client=api.LLM_CLIENT,
    )
    fake_gmail = FakeGmailClient()
    fake_gcal = FakeGCalClient()
    _seed_conflict(fake_gcal)

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
            started = client.post("/agent/demo/start", json={"script_id": "flagship_conflict"})
            assert started.status_code == 200
            work_item_id = started.json()["work_item_id"]

            invalid = client.post(
                f"/agent/work-items/{work_item_id}/respond",
                json={"action": "choose", "payload": {"choice": "invalid-choice"}},
            )
            assert invalid.status_code == 400

            listed = client.get("/agent/work-items?status=pending")
            assert listed.status_code == 200
            assert listed.json()["work_items"][0]["type"] == "conflict_decision"

            choose = client.post(
                f"/agent/work-items/{work_item_id}/respond",
                json={"action": "choose", "payload": {"choice": "keep_existing"}},
            )
            assert choose.status_code == 200
            assert choose.json()["pending_work_item"] is True

            draft_work_item_id = choose.json()["work_item_id"]
            approve = client.post(
                f"/agent/work-items/{draft_work_item_id}/respond",
                json={"action": "approve", "payload": {}},
            )
            assert approve.status_code == 200
            assert approve.json()["success"] is True
            assert approve.json()["thread"]["status"] == "completed"
    finally:
        api.app.dependency_overrides.clear()
        runtime.close()


def test_replace_agent_runtime_clear_state_resets_demo_thread_state(monkeypatch, tmp_path):
    api = _load_api(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "LLM_CLIENT", FakeLLMClient())
    monkeypatch.setattr(api.settings, "AGENT_APPROVALS_PATH", tmp_path / "approvals.json")
    monkeypatch.setattr(api.settings, "AGENT_WORK_ITEMS_PATH", tmp_path / "work_items.json")
    monkeypatch.setattr(api.settings, "AGENT_THREADS_PATH", tmp_path / "threads.json")
    monkeypatch.setattr(api.settings, "AGENT_TIMELINE_PATH", tmp_path / "timeline.json")
    monkeypatch.setattr(api.settings, "AGENT_RUNS_PATH", tmp_path / "runs.json")
    monkeypatch.setattr(api.settings, "AGENT_CHECKPOINTS_PATH", tmp_path / "checkpoints.sqlite")
    monkeypatch.setattr(api.settings, "AGENT_MEMORY_DIR", tmp_path / "memory")

    runtime = api.AgentRuntime(
        checkpoint_path=tmp_path / "checkpoints.sqlite",
        approvals_path=tmp_path / "approvals.json",
        work_items_path=tmp_path / "work_items.json",
        threads_path=tmp_path / "threads.json",
        timeline_path=tmp_path / "timeline.json",
        runs_path=tmp_path / "runs.json",
        memory_dir=tmp_path / "memory",
        llm_client=api.LLM_CLIENT,
    )
    fake_gmail = FakeGmailClient()
    fake_gcal = FakeGCalClient()
    _seed_conflict(fake_gcal)

    monkeypatch.setattr(api, "AGENT_RUNTIME", runtime)

    started = runtime.start_demo(
        script_id="flagship_conflict",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        mode="semi_auto",
    )
    choose = runtime.resume_work_item(
        work_item_id=started["work_item_id"],
        action="choose",
        context=make_context(
            runtime=runtime,
            thread_id=started["thread_id"],
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
            source="demo",
        ),
        payload={"choice": "accept_new"},
    )
    runtime.resume_work_item(
        work_item_id=choose["work_item_id"],
        action="approve",
        context=make_context(
            runtime=runtime,
            thread_id=started["thread_id"],
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
            source="demo",
        ),
        payload={},
    )

    replacement = api._replace_agent_runtime(clear_state=True)
    try:
        assert replacement.get_thread("demo-flagship-conflict")["status"] == "ready"
        assert replacement.list_work_items(status="pending", limit=50) == []
        assert replacement.list_threads(limit=50)
        _seed_conflict(fake_gcal)
        restarted = replacement.start_demo(
            script_id="flagship_conflict",
            user_id="tester@example.com",
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
        )
        next_step = replacement.resume_work_item(
            work_item_id=restarted["work_item_id"],
            action="choose",
            context=make_context(
                runtime=replacement,
                thread_id=restarted["thread_id"],
                gmail_client=fake_gmail,
                gcal_client=fake_gcal,
                mode="semi_auto",
                source="demo",
            ),
            payload={"choice": "accept_new"},
        )
        final_result = replacement.resume_work_item(
            work_item_id=next_step["work_item_id"],
            action="approve",
            context=make_context(
                runtime=replacement,
                thread_id=restarted["thread_id"],
                gmail_client=fake_gmail,
                gcal_client=fake_gcal,
                mode="semi_auto",
                source="demo",
            ),
            payload={},
        )

        assert final_result["success"] is True
        assert final_result["message"] != "Stopped because the agent reached its step limit."
        assert len(fake_gmail.created_drafts) == 2
        assert replacement.get_thread("demo-flagship-conflict")["status"] == "completed"
    finally:
        replacement.close()
