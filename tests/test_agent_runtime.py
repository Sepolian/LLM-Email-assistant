from conftest import FakeLLMClient, make_context


def test_semi_auto_requires_approval_for_calendar_write(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="schedule a meeting tomorrow at 2pm about roadmap",
        thread_id="chat-semi-auto",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="semi_auto",
    )

    assert result["pending_approval"] is True
    approvals = runtime.list_approvals(status="pending")
    assert len(approvals) == 1
    assert approvals[0]["tool_name"] == "create_calendar_event"
    assert fake_gcal.created == []


def test_auto_mode_executes_calendar_write_without_approval(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="schedule a meeting tomorrow at 2pm about roadmap",
        thread_id="chat-auto",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="auto",
    )

    assert result["success"] is True
    assert not result.get("pending_approval")
    assert fake_gcal.created
    assert fake_gcal.created[0]["title"] == "roadmap"


def test_shadow_mode_skips_write_side_effects(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="schedule a meeting tomorrow at 2pm about roadmap",
        thread_id="chat-shadow",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="auto",
        shadow_mode=True,
    )

    assert result["success"] is True
    assert fake_gcal.created == []
    created_call = next(call for call in result["tool_calls"] if call["tool_name"] == "create_calendar_event")
    assert created_call["result"]["shadow_mode"] is True


def test_resume_approval_with_edit_updates_tool_args(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="schedule a meeting tomorrow at 2pm about roadmap",
        thread_id="chat-edit",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="semi_auto",
    )

    approval_id = result["approval_id"]
    approval = runtime.approval_store.get(approval_id)
    edited_proposal = dict(approval["tool_args"]["proposal"])
    edited_proposal["title"] = "roadmap revised"

    resumed = runtime.resume_approval(
        approval_id=approval_id,
        action="edit",
        context=make_context(
            runtime=runtime,
            thread_id="chat-edit",
            gmail_client=fake_gmail,
            gcal_client=fake_gcal,
            mode="semi_auto",
        ),
        tool_args={"proposal": edited_proposal},
    )

    assert resumed["success"] is True
    assert fake_gcal.created[0]["title"] == "roadmap revised"
    assert runtime.approval_store.get(approval_id)["status"] == "approved"


def test_chat_in_chinese_can_search_emails(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="帮我找预算相关的邮件",
        thread_id="chat-zh-search",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="semi_auto",
    )

    assert result["success"] is True
    assert result["tool_calls"][0]["tool_name"] == "search_emails"
    assert result["tool_calls"][0]["result"]["count"] >= 1


def test_chat_calendar_inspection_stays_read_only(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="show my upcoming calendar events",
        thread_id="chat-calendar-list",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="semi_auto",
    )

    assert result["success"] is True
    assert not result.get("pending_approval")
    assert result["tool_calls"][0]["tool_name"] == "list_calendar_events"


def test_chat_in_chinese_can_schedule_with_approval(runtime_factory, fake_gmail, fake_gcal):
    runtime = runtime_factory()

    result = runtime.run_chat(
        message="帮我安排一个明天下午两点关于路线图的会议",
        thread_id="chat-zh-schedule",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[],
        automation_settings={"auto_add_events": False},
        mode="semi_auto",
    )

    assert result["success"] is True
    assert result["pending_approval"] is True
    assert result["tool_calls"][0]["tool_name"] == "create_calendar_event"
