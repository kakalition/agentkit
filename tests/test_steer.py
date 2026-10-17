from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit.config import AgentSettings
from agentkit.db.repositories import Repositories
from agentkit.deps import Deps
from agentkit.errors import SteeringUnavailable
from agentkit.foundation import App
from agentkit.runtime import Runtime
from agentkit.session import ChatRunner, TurnHandle


def _app(tmp_path, model) -> App:  # noqa: ANN001
    app = App(
        settings=AgentSettings(owner_id="owner", agent_home=tmp_path),
        discover=False,
        model=model,
    )
    app.agent(Agent(model, output_type=str))
    return app


def _agent() -> Agent:
    return Agent(name="a", deps_type=Deps, output_type=str, instructions="x")


def _text_of(messages: list[ModelMessage]) -> str:
    return "\n".join(str(part) for message in messages for part in getattr(message, "parts", []))


class _GatedModel:
    """A FunctionModel whose first request blocks until the test releases it."""

    def __init__(self, first: str = "first", rest: str = "second") -> None:
        self.calls: list[list[ModelMessage]] = []
        self.started = asyncio.Event()
        self.gate = asyncio.Event()
        self._first = first
        self._rest = rest

    def build(self) -> FunctionModel:
        async def model_fn(messages, info):  # noqa: ANN001
            self.calls.append(list(messages))
            if len(self.calls) == 1:
                self.started.set()
                await self.gate.wait()
                return ModelResponse(parts=[TextPart(self._first)])
            return ModelResponse(parts=[TextPart(self._rest)])

        return FunctionModel(model_fn)


async def test_steer_asap_delivered_mid_run(runtime: Runtime, repos: Repositories):
    gated = _GatedModel()
    deps = Deps(settings=runtime.settings, repos=repos, model=gated.build())
    runner = ChatRunner(deps, agent=_agent(), conversation_id="cli:steer")

    task = asyncio.create_task(runner.send("hello"))
    await asyncio.wait_for(gated.started.wait(), timeout=5)
    assert runner.turn is not None
    enqueue_id = await runner.steer("steer this now", priority="asap")
    assert enqueue_id
    gated.gate.set()
    result = await asyncio.wait_for(task, timeout=5)

    assert result.output == "second"
    assert len(gated.calls) == 2
    assert "steer this now" in _text_of(gated.calls[1])


async def test_steer_when_idle_does_not_interrupt(runtime: Runtime, repos: Repositories):
    gated = _GatedModel()
    deps = Deps(settings=runtime.settings, repos=repos, model=gated.build())
    runner = ChatRunner(deps, agent=_agent(), conversation_id="cli:idle")

    task = asyncio.create_task(runner.send("hello"))
    await asyncio.wait_for(gated.started.wait(), timeout=5)
    await runner.steer("follow up later", priority="when_idle")
    gated.gate.set()
    result = await asyncio.wait_for(task, timeout=5)

    # The in-flight request completed intact; the queued message arrives only after.
    assert result.output == "second"
    assert "follow up later" not in _text_of(gated.calls[0])
    assert "follow up later" in _text_of(gated.calls[1])


async def test_steer_without_running_turn_raises(runtime: Runtime, repos: Repositories):
    deps = Deps(settings=runtime.settings, repos=repos, model=_GatedModel().build())
    runner = ChatRunner(deps, agent=_agent(), conversation_id="cli:idle")
    with pytest.raises(SteeringUnavailable):
        await runner.steer("anything")


async def test_turn_handle_forwards_priority():
    recorded: dict[str, object] = {}

    class FakeRun:
        run_id = "run-1"

        def enqueue(self, text, *, priority="asap"):
            recorded["text"] = text
            recorded["priority"] = priority
            return "enq-1"

    handle = TurnHandle("cli:x", FakeRun())
    assert handle.run_id == "run-1"
    assert handle.enqueue("hi", priority="when_idle") == "enq-1"
    assert recorded == {"text": "hi", "priority": "when_idle"}


async def test_app_steer_reaches_running_turn(tmp_path):
    gated = _GatedModel()
    app = _app(tmp_path, gated.build())
    task = asyncio.create_task(app.run("hello", conversation_id="cli:app"))
    await asyncio.wait_for(gated.started.wait(), timeout=5)
    assert "cli:app" in app.running()
    enqueue_id = await app.steer("cli:app", "app steer", priority="asap")
    assert enqueue_id
    gated.gate.set()
    await asyncio.wait_for(task, timeout=5)
    assert "app steer" in _text_of(gated.calls[1])


async def test_app_steer_without_running_turn_raises(tmp_path):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")]))
    app = _app(tmp_path, model)
    with pytest.raises(SteeringUnavailable):
        await app.steer("cli:idle", "nope")


async def test_cancel_still_stops_running_turn(tmp_path):
    gated = _GatedModel()
    app = _app(tmp_path, gated.build())
    task = asyncio.create_task(app.run("hello", conversation_id="cli:cancel"))
    await asyncio.wait_for(gated.started.wait(), timeout=5)
    assert app.cancel("cli:cancel") is True
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
