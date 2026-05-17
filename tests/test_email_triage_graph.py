from conftest import FakeLLMClient


def test_email_triage_graph_runs_multi_step_sequence(runtime_factory, fake_gmail, fake_gcal):
    llm = FakeLLMClient(
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
        matches=[
            {
                "rule_id": "finance-rule",
                "confidence": 0.92,
                "explanation": "Budget-related message.",
            }
        ],
    )
    runtime = runtime_factory(llm_client=llm)
    queued = []

    def proposal_writer(proposal, email_id, email_subject, email_summary):
        entry = {
            "id": f"proposal-{len(queued) + 1}",
            "title": proposal["title"],
            "start": proposal["start"],
            "end": proposal["end"],
            "email_id": email_id,
            "email_subject": email_subject,
            "email_summary": email_summary,
        }
        queued.append(entry)
        return entry

    result = runtime.run_email_triage(
        email_id="email-1",
        user_id="tester@example.com",
        gmail_client=fake_gmail,
        gcal_client=fake_gcal,
        rules=[{"id": "finance-rule", "label": "Finance", "reason": "Budget or finance related"}],
        automation_settings={"auto_add_events": False},
        mode="auto",
        proposal_writer=proposal_writer,
    )

    tool_names = [call["tool_name"] for call in result["tool_calls"]]
    assert tool_names == [
        "evaluate_label_rules",
        "summarize_email",
        "list_calendar_events",
        "queue_event_proposal",
        "apply_label",
    ]
    assert queued and queued[0]["title"] == "Budget Sync"
    assert fake_gmail.applied_labels[0]["message_id"] == "email-1"
    assert result["proposals_queued"] == 1
    assert result["labels_applied"] == 1
