from llm_email_app.agent.memory.store import MarkdownMemoryStore


def test_markdown_memory_store_writes_and_retrieves(tmp_path):
    store = MarkdownMemoryStore(tmp_path / "memory")

    written = store.write_candidates(
        user_id="tester@example.com",
        thread_id="thread-1",
        candidates=[
            {
                "type": "semantic",
                "scope": "user",
                "scope_id": "tester@example.com",
                "content": "User prefers Tuesday morning meetings.",
                "confidence": 0.9,
                "source": "test",
            },
            {
                "type": "semantic",
                "scope": "user",
                "scope_id": "tester@example.com",
                "content": "User prefers Tuesday morning meetings.",
                "confidence": 0.9,
                "source": "test",
            },
            {
                "type": "episodic",
                "scope": "thread",
                "scope_id": "thread-1",
                "content": "Budget review was discussed with Alice.",
                "confidence": 0.7,
                "source": "test",
            },
        ],
    )

    assert len(written) == 2
    files = list((tmp_path / "memory").rglob("*.md"))
    assert files
    assert files[0].read_text(encoding="utf-8").startswith("---\n")

    results = store.search("tester@example.com", query="Tuesday morning", limit=5)
    assert results
    assert "Tuesday morning" in results[0]["content"]

    context = store.build_context("tester@example.com", query="budget")
    assert context["count"] >= 1
