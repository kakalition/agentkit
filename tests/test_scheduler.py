from __future__ import annotations

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


def test_schedule_cron_and_run(sched):
    calls: list[dict] = []

    @sched.task("noop")
    def noop(**kwargs):
        calls.append(kwargs)

    sched.schedule_cron("c", "* * * * *", "noop", args={"x": 1})
    fired = sched.run_due_now(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    assert fired == ["c"]
    assert calls == [{"x": 1}]

    jobs = {job["name"]: job for job in sched.list_jobs()}
    assert jobs["c"]["run_count"] == 1
    assert jobs["c"]["kind"] == "cron"


def test_schedule_once_disables_after_run(sched):
    sched.task("noop2")(lambda **kwargs: None)
    sched.schedule_once("o", datetime(2026, 1, 1, 0, 0, tzinfo=UTC), "noop2")
    sched.run_due_now(datetime(2026, 1, 1, 0, 5, tzinfo=UTC))
    assert sched.list_jobs()[0]["enabled"] is False


def test_remove_job(sched):
    sched.task("noop3")(lambda **kwargs: None)
    sched.schedule_cron("temp", "0 0 * * *", "noop3")
    assert sched.remove_job("temp") is True
    assert sched.list_jobs() == []


def test_invalid_cron_rejected(sched):
    with pytest.raises(ValueError):
        sched.schedule_cron("bad", "not a cron", "t")


def test_tick_accepts_dbos_scheduled_signature():
    import inspect

    # DBOS invokes scheduled workflows as fn(scheduled_time, context).
    params = list(inspect.signature(scheduler.tick).parameters)
    assert len(params) >= 2
