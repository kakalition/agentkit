from __future__ import annotations

from agentkit.agents.handle import AgentHandle
from agentkit.agents.handoff import handoff
from agentkit.agents.registry import AgentRegistry
from agentkit.deps import Deps
from agentkit.foundation.events import Dispatcher
from agentkit.session import serialize_message


class RecordingAgent:
    def __init__(self, output: str = "handled") -> None:
        self.output = output
        self.calls: list[dict] = []

    async def run(self, prompt, *, deps=None, usage=None, model=None, message_history=None, **kw):
        self.calls.append({"prompt": prompt, "history": message_history})
        return type("Result", (), {"output": self.output})()


async def _deps(deps: Deps) -> Deps:
    from pydantic_ai.messages import ModelResponse, TextPart

    repos = deps.repos
    await repos.conversations.get_or_create("cli:1")
    await repos.messages.append(
        "cli:1", [serialize_message(ModelResponse(parts=[TextPart("earlier")]))]
    )
    deps.extras["conversation_id"] = "cli:1"
    return deps


async def test_handoff_default_passes_full_transcript(deps: Deps):
    deps = await _deps(deps)
    target = RecordingAgent()
    reply = await handoff(target, ctx=type("Ctx", (), {"deps": deps})())
    assert reply == "handled"
    call = target.calls[0]
    assert call["history"] and len(call["history"]) == 1
    assert "Continue" in call["prompt"]


async def test_handoff_brief_sends_only_the_brief(deps: Deps):
    deps = await _deps(deps)
    target = RecordingAgent()
    reply = await handoff(target, brief="just translate this", ctx=type("Ctx", (), {"deps": deps})())
    assert reply == "handled"
    call = target.calls[0]
    assert call["history"] is None
    assert call["prompt"] == "just translate this"


async def test_handoff_max_guard_stops_the_chain(deps: Deps):
    deps = await _deps(deps)
    deps.settings.max_handoffs = 2
    deps.extras["_handoff_depth"] = 2  # already at the limit
    target = RecordingAgent()
    events = Dispatcher()
    errors: list[str] = []
    events.listen("agent.error", lambda e: errors.append(e.get("error")))
    reply = await handoff(target, ctx=type("Ctx", (), {"deps": deps})(), events=events)
    assert "limit reached" in reply
    assert target.calls == []
    assert errors == ["max_handoffs exceeded"]


async def test_handoff_emits_event_and_increments_depth(deps: Deps):
    deps = await _deps(deps)
    events = Dispatcher()
    seen: list[int] = []
    events.listen("agent.handoff", lambda e: seen.append(e.get("depth")))
    await handoff(RecordingAgent(), ctx=type("Ctx", (), {"deps": deps})(), events=events)
    assert seen == [1]
    assert deps.extras["_handoff_depth"] == 1


async def test_handoff_by_registry_name(deps: Deps):
    deps = await _deps(deps)
    registry = AgentRegistry()
    registry.register(AgentHandle.local(RecordingAgent(output="named"), name="translator"))
    reply = await handoff(
        "translator", registry=registry, ctx=type("Ctx", (), {"deps": deps})()
    )
    assert reply == "named"


async def test_handoff_unknown_agent(deps: Deps):
    deps = await _deps(deps)
    registry = AgentRegistry()
    reply = await handoff("ghost", registry=registry, ctx=type("Ctx", (), {"deps": deps})())
    assert "no such agent" in reply
