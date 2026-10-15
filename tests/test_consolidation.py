from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentkit.consolidation import CONSOLIDATE_TASK, consolidate_memories, register_consolidate_task
from agentkit.db.repositories import Repositories


async def test_consolidate_merges_duplicates_and_prunes(repos: Repositories):
    await repos.memories.add("The user likes strong coffee")
    await repos.memories.add("The user likes strong coffee")
    past = datetime.now(UTC) - timedelta(days=1)
    await repos.memories.add("old appointment", kind="episodic", expires_at=past)

    summary = await consolidate_memories(repos, duplicate_threshold=0.9, group_limit=50)

    assert summary["pruned"] == 1
    assert summary["merged"] >= 1
    contents = [row.content for row in await repos.memories.list()]
    assert contents.count("The user likes strong coffee") == 1
    assert "old appointment" not in contents


async def test_consolidate_summarizes_long_group(repos: Repositories):
    for index in range(10):
        await repos.memories.add(f"fact number {index} about topic {index}", kind="fact")
    summary = await consolidate_memories(repos, group_limit=8)
    assert summary["summarized"] == 9
    assert len(await repos.memories.list(kind="fact")) == 1


async def test_consolidate_dry_run_changes_nothing(repos: Repositories):
    await repos.memories.add("The user likes strong coffee")
    await repos.memories.add("The user likes strong coffee")
    before = len(await repos.memories.list())
    summary = await consolidate_memories(repos, duplicate_threshold=0.9, dry_run=True)
    assert summary["merged"] >= 1
    assert len(await repos.memories.list()) == before


async def test_consolidate_summarizer_override(repos: Repositories):
    for index in range(9):
        await repos.memories.add(f"unique fact {index}", kind="preference")
    await consolidate_memories(repos, group_limit=8, summarizer=lambda contents: "COMBINED")
    rows = await repos.memories.list(kind="preference")
    assert len(rows) == 1
    assert rows[0].content == "COMBINED"


def test_register_consolidate_task():
    assert register_consolidate_task() == CONSOLIDATE_TASK
    from agentkit.scheduler import TASKS

    assert CONSOLIDATE_TASK in TASKS
