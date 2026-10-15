from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentkit import Agent, scheduler
from agentkit.deps import Deps

CALLS: list[dict] = []


@scheduler.task("tools.echo")
def _echo(**kwargs) -> None:
    CALLS.append(kwargs)


@pytest.fixture(autouse=True)
def _clear_calls():
    CALLS.clear()
    yield
    CALLS.clear()


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent(tasks=None):
    return Agent.make("s").instructions("x").scheduler(tasks=tasks).output(str).build()


def test_scheduler_approval_flags():
    agent = _agent(["tools.echo"])
    assert agent._function_toolset.tools["schedule_task"].requires_approval is True
    assert agent._function_toolset.tools["run_schedule_now"].requires_approval is True
    assert agent._function_toolset.tools["list_schedules"].requires_approval is False


async def test_schedule_lifecycle(repos, deps: Deps):
    agent = _agent(["tools.echo"])
    ctx = _ctx(deps)

    assert "scheduled" in await _fn(agent, "schedule_task")(
        ctx, "nightly", "tools.echo", cron="0 8 * * *", args={"a": 1}
    )
    job = await repos.schedules.get("nightly")
    assert job is not None and job.task == "tools.echo"
    assert "nightly" in await _fn(agent, "list_schedules")(ctx)
    assert "nightly" in await _fn(agent, "get_schedule")(ctx, "nightly")

    assert "invalid cron" in await _fn(agent, "schedule_task")(
        ctx, "bad", "tools.echo", cron="not-a-cron"
    )
    assert (await _fn(agent, "schedule_task")(ctx, "both", "tools.echo", cron="* * * * *", at="2026-01-01T00:00")).startswith("ERROR")

    await _fn(agent, "run_schedule_now")(ctx, "nightly")
    assert CALLS == [{"a": 1}]

    assert "disabled" in await _fn(agent, "cancel_schedule")(ctx, "nightly")
    assert (await repos.schedules.get("nightly")).enabled is False
    assert "removed" in await _fn(agent, "cancel_schedule")(ctx, "nightly", delete=True)
    assert await repos.schedules.get("nightly") is None


async def test_schedule_task_allow_list(repos, deps: Deps):
    agent = _agent(["tools.echo"])
    assert (await _fn(agent, "schedule_task")(_ctx(deps), "x", "other.task", cron="* * * * *")).startswith("ERROR")
    # One-off schedule.
    assert "scheduled" in await _fn(agent, "schedule_task")(
        _ctx(deps), "once", "tools.echo", at="2026-01-01T09:00"
    )
