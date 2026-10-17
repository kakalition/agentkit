"""WS8 — chains, batches, and job middleware."""

from __future__ import annotations

import inspect
from typing import Any

from agentkit import Batch, Chain, Job, batch, chain, pending_batches


class FakeBus:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def dispatch(self, job: Any) -> Any:
        self.calls.append(job)
        if isinstance(job, Job):
            return await job.dispatch(self)
        result = job(self)
        if inspect.isawaitable(result):
            result = await result
        return result


class Record(Job):
    def __init__(self, log: list[str], tag: str) -> None:
        self.log = log
        self.tag = tag

    def handle(self, app: Any) -> None:  # noqa: ARG002
        self.log.append(self.tag)


class Boom(Job):
    def handle(self, app: Any) -> None:  # noqa: ARG002
        raise RuntimeError("boom")


class Traced(Job):
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def middleware(self) -> list[Any]:
        async def trace(job: Any, app: Any, call_next: Any) -> Any:  # noqa: ARG001
            self.log.append("before")
            result = await call_next()
            self.log.append("after")
            return result

        return [trace]

    def handle(self, app: Any) -> None:  # noqa: ARG002
        self.log.append("handle")


class Recovering(Job):
    def __init__(self) -> None:
        self.failed_with: BaseException | None = None

    def handle(self, app: Any) -> None:  # noqa: ARG002
        raise ValueError("nope")

    def failed(self, app: Any, error: BaseException) -> None:  # noqa: ARG002
        self.failed_with = error


async def test_chain_runs_in_order_with_then() -> None:
    app = FakeBus()
    log: list[str] = []
    done: list[str] = []
    await chain(Record(log, "a"), Record(log, "b")).then(lambda: done.append("done")).dispatch(app)
    assert log == ["a", "b"]
    assert done == ["done"]


async def test_chain_catch_on_failure() -> None:
    app = FakeBus()
    caught: list[str] = []
    await chain(Record([], "a"), Boom()).catch(lambda exc: caught.append(str(exc))).dispatch(app)
    assert caught == ["boom"]


async def test_batch_progress_and_callbacks() -> None:
    app = FakeBus()
    log: list[str] = []
    finished: list[Batch] = []
    result = await batch([Record(log, "a"), Record(log, "b"), Record(log, "c")]).then(
        finished.append
    ).dispatch(app)
    assert result.progress() == (3, 3)
    assert result.pending == 0
    assert log == ["a", "b", "c"]
    assert finished and finished[0] is result
    assert result in pending_batches()


async def test_batch_catch_partial_failure() -> None:
    app = FakeBus()
    log: list[str] = []
    errors: list[str] = []
    result = await batch([Record(log, "a"), Boom(), Record(log, "b")]).catch(
        lambda _batch, exc: errors.append(str(exc))
    ).dispatch(app)
    assert errors == ["boom"]
    assert result.progress() == (3, 3)
    assert len(result.failures) == 1
    assert log == ["a", "b"]  # failing job does not stop the rest


async def test_job_middleware_wraps_handle() -> None:
    app = FakeBus()
    log: list[str] = []
    await Traced(log).dispatch(app)
    assert log == ["before", "handle", "after"]


async def test_job_failed_hook_receives_error() -> None:
    app = FakeBus()
    job = Recovering()
    try:
        await job.dispatch(app)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    assert isinstance(job.failed_with, ValueError)


def test_chain_and_batch_builders() -> None:
    assert isinstance(chain(Record([], "x")), Chain)
    assert isinstance(batch([Record([], "x")]), Batch)
    single = batch(Record([], "x"))
    assert single.total == 1
