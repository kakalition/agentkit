from __future__ import annotations

from agentkit.db.repositories import Repositories


def test_conversation_and_messages(repos: Repositories):
    repos.conversations.get_or_create("cli:1")
    repos.messages.append("cli:1", ['{"a": 1}', '{"b": 2}'])
    assert repos.messages.next_seq("cli:1") == 2
    assert [m.seq for m in repos.messages.list("cli:1")] == [0, 1]
    repos.messages.clear("cli:1")
    assert repos.messages.list("cli:1") == []


def test_a2a_task_repo(repos: Repositories):
    repos.a2a.upsert("t1", "owner", "c1", "TASK_STATE_COMPLETED", '{"id":"t1"}')
    record = repos.a2a.get("t1")
    assert record is not None and record.state == "TASK_STATE_COMPLETED"
    repos.a2a.upsert("t1", "owner", "c1", "TASK_STATE_FAILED", '{"id":"t1"}')
    assert repos.a2a.get("t1").state == "TASK_STATE_FAILED"
    repos.a2a.delete("t1")
    assert repos.a2a.get("t1") is None
