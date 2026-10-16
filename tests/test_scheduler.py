from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from agentkit import scheduler
from agentkit.config import AgentSettings
from agentkit.db.models import ScheduledJob
from agentkit.runtime import build_runtime


@pytest.fixture
def sched(tmp_path):
    runtime = build_runtime(AgentSettings(owner_id="owner", agent_home=tmp_path))
    scheduler._runtime = runtime  # non-DBOS path for tests
    yield scheduler
    scheduler._runtime = None


def test_due_cron_matches_minute():
    job = ScheduledJob(name="a", kind="cron", schedule="0 8 * * *", task="t", enabled=True)
    assert scheduler.due_jobs([job], datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
    assert not scheduler.due_jobs([job], datetime(2026, 1, 1, 9, 0, tzinfo=UTC))


def test_due_once():
    job = ScheduledJob(
        name="b", kind="once", schedule="2026-01-01T09:00:00+00:00", task="t", enabled=True
    )
    assert scheduler.due_jobs([job], datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
    assert not scheduler.due_jobs([job], datetime(2026, 1, 1, 8, 0, tzinfo=UTC))


def test_disabled_job_not_due():
    job = ScheduledJob(name="c", kind="cron", schedule="* * * * *", task="t", enabled=False)
    assert scheduler.due_jobs([job], datetime(2026, 1, 1, 0, 0, tzinfo=UTC)) == []


async def test_schedule_cron_and_run(sched):
    calls: list[dict] = []

    @sched.task("noop")
    def noop(**kwargs):
        calls.append(kwargs)

    await sched.schedule_cron("c", "* * * * *", "noop", args={"x": 1})
    fired = await sched.run_due_now(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert fired == ["c"]
    assert calls == [{"x": 1}]

    jobs = {job["name"]: job for job in await sched.list_jobs()}
    assert jobs["c"]["run_count"] == 1
    assert jobs["c"]["kind"] == "cron"


async def test_schedule_once_disables_after_run(sched):
    sched.task("noop2")(lambda **kwargs: None)
    await sched.schedule_once("o", datetime(2026, 1, 1, 0, 0, tzinfo=UTC), "noop2")
    await sched.run_due_now(datetime(2026, 1, 1, 0, 5, tzinfo=UTC))
    assert (await sched.list_jobs())[0]["enabled"] is False


async def test_remove_job(sched):
    sched.task("noop3")(lambda **kwargs: None)
    await sched.schedule_cron("temp", "0 0 * * *", "noop3")
    assert await sched.remove_job("temp") is True
    assert await sched.list_jobs() == []


async def test_invalid_cron_rejected(sched):
    with pytest.raises(ValueError):
        await sched.schedule_cron("bad", "not a cron", "t")


def test_tick_accepts_dbos_scheduled_signature():
    import inspect

    # DBOS invokes scheduled workflows as fn(scheduled_time, context).
    params = list(inspect.signature(scheduler.tick).parameters)
    assert len(params) >= 2


# -- result delivery --------------------------------------------------------
async def test_invoke_task_delivers_result_to_origin(sched):
    delivered: list[tuple[str, str]] = []
    sched.set_result_sink(lambda cid, text: delivered.append((cid, text)))

    @sched.task("report")
    def report(**kwargs):
        return "done!"

    try:
        await sched.invoke_task("report", json.dumps({"_deliver_to": "cli:1"}))
        assert delivered == [("cli:1", "done!")]

        # No ``_deliver_to`` -> no delivery.
        await sched.invoke_task("report", "{}")
        assert delivered == [("cli:1", "done!")]
    finally:
        sched.set_result_sink(None)


async def test_invoke_task_strips_deliver_to_from_kwargs(sched):
    seen: dict = {}

    @sched.task("inspect")
    def inspect(**kwargs):
        seen.update(kwargs)

    await sched.invoke_task("inspect", json.dumps({"_deliver_to": "cli:1", "x": 2}))
    assert seen == {"x": 2}


async def test_result_sink_failure_is_best_effort(sched):
    def boom(cid, text):
        raise RuntimeError("nope")

    sched.set_result_sink(boom)

    @sched.task("safe")
    def safe(**kwargs):
        return 42

    try:
        assert await sched.invoke_task("safe", json.dumps({"_deliver_to": "cli:1"})) == 42
    finally:
        sched.set_result_sink(None)


async def test_app_deliver_result_maps_channel(tmp_path):
    from agentkit.foundation.application import App

    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")
    app = App(name="deliver", settings=settings, discover=False)
    app.boot()

    telegram: list[str | None] = []
    app.notifier.channel(
        "telegram", lambda notification, *, conversation_id=None: telegram.append(conversation_id)
    )
    app._deliver_result("telegram:42", "task done")
    assert telegram == ["telegram:42"]

    # A webui conversation has no channel sender -> falls back to ``conversation``
    # (writes into chat history).
    app._deliver_result("webui:default", "hello")
    async with app.repositories() as repos:
        payloads = await repos.messages.list("webui:default")
    assert payloads
