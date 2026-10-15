from __future__ import annotations

from agentkit.db.repositories import Repositories


async def test_conversation_and_messages(repos: Repositories):
    await repos.conversations.get_or_create("cli:1")
    await repos.messages.append("cli:1", ['{"a": 1}', '{"b": 2}'])
    assert await repos.messages.next_seq("cli:1") == 2
    assert [m.seq for m in await repos.messages.list("cli:1")] == [0, 1]
    await repos.messages.clear("cli:1")
    assert await repos.messages.list("cli:1") == []


async def test_a2a_task_repo(repos: Repositories):
    await repos.a2a.upsert("t1", "owner", "c1", "TASK_STATE_COMPLETED", '{"id":"t1"}')
    record = await repos.a2a.get("t1")
    assert record is not None and record.state == "TASK_STATE_COMPLETED"
    await repos.a2a.upsert("t1", "owner", "c1", "TASK_STATE_FAILED", '{"id":"t1"}')
    refreshed = await repos.a2a.get("t1")
    assert refreshed is not None and refreshed.state == "TASK_STATE_FAILED"
    await repos.a2a.delete("t1")
    assert await repos.a2a.get("t1") is None
