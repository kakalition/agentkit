"""WS3.2 — online scoring of live run traces."""

from __future__ import annotations

from typing import Any

from agentkit.foundation.application import App
from agentkit.foundation.facade import using
from agentkit.runs import RunEvent
from agentkit.runtime import Runtime
from agentkit.scorers import OnlineScorer, score_run


async def _write_run(repos: Any, run_id: str, *, tools: list[str], error: bool = False) -> None:
    events = [RunEvent(kind="start", run_id=run_id)]
    events += [RunEvent(kind="tool", run_id=run_id, tool=tool) for tool in tools]
    if error:
        events.append(RunEvent(kind="error", run_id=run_id, text="boom"))
    events.append(RunEvent(kind="final", run_id=run_id, data={"output": "done"}))
    await repos.run_events.add_many(run_id, [event.to_dict() for event in events])


async def test_score_run_records_result(runtime: Runtime, repos: Any) -> None:
    await _write_run(repos, "run-1", tools=["search", "write"])
    result = await score_run(repos, "run-1")
    assert result["passed"] is True
    assert result["record_id"] is not None
    assert result["tool_calls"] == ["search", "write"]
    records = await repos.eval_runs.list()
    assert any(record.dataset == "online:run-1" for record in records)


async def test_score_run_fails_on_error_trace(runtime: Runtime, repos: Any) -> None:
    await _write_run(repos, "run-2", tools=["search"], error=True)
    result = await score_run(repos, "run-2")
    assert result["passed"] is False


async def test_score_run_with_custom_grader(runtime: Runtime, repos: Any) -> None:
    await _write_run(repos, "run-3", tools=["search"])

    class Always:
        name = "always"

        def grade(self, case: Any, output: Any) -> bool:
            return True

    result = await score_run(repos, "run-3", grader=Always())
    assert result["passed"] is True


def _app(runtime: Runtime, **updates: Any) -> App:
    settings = runtime.settings.model_copy(update=updates) if updates else runtime.settings
    app = App(name="score", settings=settings, discover=False)
    app._runtime = runtime
    return app


def test_online_scorer_reads_settings(runtime: Runtime) -> None:
    app = _app(runtime)
    with using(app):
        scorer = app.online_scorer
        assert isinstance(scorer, OnlineScorer)
        assert scorer.enabled is False
        assert scorer.grader_name == "trace"

    tuned = _app(runtime, online_scoring_enabled=True, online_scoring_grader="contains")
    with using(tuned):
        assert tuned.online_scorer.enabled is True
        assert tuned.online_scorer.grader().name == "contains"


async def test_online_scorer_score_uses_app_grader(runtime: Runtime, repos: Any) -> None:
    await _write_run(repos, "run-4", tools=["search"])
    app = _app(runtime, online_scoring_grader="trace")
    with using(app):
        result = await app.online_scorer.score(repos, "run-4")
    assert result["passed"] is True


async def test_auto_score_after_run(runtime: Runtime) -> None:
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from agentkit import Agent

    settings = runtime.settings.model_copy(update={"online_scoring_enabled": True})
    app = App(name="auto", settings=settings, discover=False)
    app._runtime = runtime
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))  # noqa: ARG005
    app.agent(Agent.make("auto").instructions("x").output(str))
    app.boot()
    await app.run("hi", conversation_id="cli:auto")

    async with app.repositories() as repos:
        records = await repos.eval_runs.list()
    assert any(record.dataset == "online:cli:auto" for record in records)


async def test_auto_score_disabled_by_default(runtime: Runtime) -> None:
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from agentkit import Agent

    app = _app(runtime)
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))  # noqa: ARG005
    app.agent(Agent.make("auto").instructions("x").output(str))
    app.boot()
    await app.run("hi", conversation_id="cli:off")

    async with app.repositories() as repos:
        records = await repos.eval_runs.list()
    assert not any(record.dataset == "online:cli:off" for record in records)
