from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentkit import Agent, App, scheduler
from agentkit.config import AgentSettings
from agentkit.deps import Deps
from agentkit.foundation.queue import Job

CALLS: list[dict] = []


@scheduler.task("tools.queued")
def _queued(**kwargs) -> None:
    CALLS.append(kwargs)


class RecordJob(Job):
    def __init__(self, value: int = 0) -> None:
        self.value = value

    def handle(self, app) -> None:  # pragma: no cover - trivial
        CALLS.append({"value": self.value})


@pytest.fixture(autouse=True)
def _clear_calls():
    CALLS.clear()
    yield
    CALLS.clear()


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _agent(tasks=None, jobs=None):
    return Agent.make("q").instructions("x").scheduler(tasks=tasks).queue(jobs=jobs).output(str).build()


def _settings(tmp_path, **overrides) -> AgentSettings:
    return AgentSettings(
        agent_home=tmp_path, memory_embedding_backend="hash", webui_enabled=False, **overrides
    )


def test_queue_approval_flags():
    agent = _agent(tasks=["tools.queued"], jobs={"record": RecordJob})
    assert agent._function_toolset.tools["enqueue_task"].requires_approval is True
    assert agent._function_toolset.tools["enqueue_job"].requires_approval is True
    assert agent._function_toolset.tools["queue_status"].requires_approval is False


async def test_enqueue_task_inline_when_queue_disabled(tmp_path):
    app = App(name="q", settings=_settings(tmp_path, queue_enabled=False), discover=False)
    async with app.repositories() as repos:
        deps = Deps(settings=app.settings, repos=repos, extras={"app": app})
        ctx = SimpleNamespace(deps=deps)
        agent = _agent(tasks=["tools.queued"])
        assert "ran" in await _fn(agent, "enqueue_task")(ctx, "tools.queued", {"a": 1})
    assert CALLS == [{"a": 1}]


async def test_enqueue_task_pushes_when_queue_enabled(tmp_path):
    app = App(name="q", settings=_settings(tmp_path, queue_enabled=True), discover=False)
    async with app.repositories() as repos:
        deps = Deps(settings=app.settings, repos=repos, extras={"app": app})
        ctx = SimpleNamespace(deps=deps)
        agent = _agent(tasks=["tools.queued"])
        assert "queued" in await _fn(agent, "enqueue_task")(ctx, "tools.queued")
        assert "pending" in await _fn(agent, "queue_status")(ctx)


async def test_enqueue_task_allow_list(tmp_path):
    app = App(name="q", settings=_settings(tmp_path), discover=False)
    async with app.repositories() as repos:
        deps = Deps(settings=app.settings, repos=repos, extras={"app": app})
        ctx = SimpleNamespace(deps=deps)
        agent = _agent(tasks=["tools.queued"])
        out = await _fn(agent, "enqueue_task")(ctx, "other.task")
        assert out.startswith("ERROR")


async def test_enqueue_job_and_failed_jobs(tmp_path):
    app = App(name="q", settings=_settings(tmp_path), discover=False)
    ctx = SimpleNamespace(deps=Deps(settings=app.settings, extras={"app": app}))
    agent = _agent(jobs={"record": RecordJob})

    async with app.repositories() as repos:
        inline_ctx = SimpleNamespace(deps=Deps(settings=app.settings, repos=repos, extras={"app": app}))
        assert "ran" in await _fn(agent, "enqueue_job")(inline_ctx, "record", {"value": 7})
        assert CALLS == [{"value": 7}]
        assert (await _fn(agent, "enqueue_job")(inline_ctx, "ghost")).startswith("ERROR")

    record = await app.queue.push(RecordJob(), queue="dead")
    assert await _fn(agent, "retry_job")(ctx, 9999) == "(no such failed job)"
    async with app.repositories() as repos:
        row = await repos.queue.get(record)
        row.failed = True
        row.error = "boom"
        repos.session.add(row)
    assert "RecordJob" in await _fn(agent, "list_failed_jobs")(ctx)
    assert "requeued" in await _fn(agent, "retry_job")(ctx, record)
