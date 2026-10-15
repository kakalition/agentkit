from __future__ import annotations

from agentkit.agents.handle import AgentHandle
from agentkit.agents.registry import AgentRegistry
from agentkit.foundation.events import Dispatcher
from agentkit.orchestrator import Orchestrator, Supervisor, run_all_agents


class EchoAgent:
    def __init__(self, output: str = "ok") -> None:
        self.output = output

    async def run(self, prompt, *, deps=None, usage=None, model=None, **kwargs):
        return type("Result", (), {"output": f"{self.output}:{prompt}"})()


class ExplodingAgent:
    async def run(self, *args, **kwargs):
        raise RuntimeError("nope")


class Ctx:
    deps = None
    usage = None


def test_orchestrator_routes_by_capability():
    orchestrator = Orchestrator(name="lead", instructions="route")
    orchestrator.add_specialist(
        EchoAgent(), name="researcher", tool_name="research", capabilities=["search"]
    )
    assert orchestrator.route("search").name == "researcher"
    assert orchestrator.route("researcher").name == "researcher"
    assert orchestrator.route("missing") is None
    assert "research" in set(orchestrator.agent._function_toolset.tools.keys())


async def test_orchestrator_emits_lifecycle_events():
    events = Dispatcher()
    seen: list[tuple[str, str]] = []
    events.listen("agent.started", lambda e: seen.append(("started", e.agent)))
    events.listen("agent.finished", lambda e: seen.append(("finished", e.agent)))
    orchestrator = Orchestrator(name="lead", instructions="route", events=events)
    orchestrator.add_specialist(EchoAgent(), name="worker", tool_name="work")
    reply = await orchestrator.invoke(Ctx(), "worker", "do it")
    assert reply == "ok:do it"
    assert ("started", "worker") in seen and ("finished", "worker") in seen


async def test_orchestrator_falls_back_on_failure():
    events = Dispatcher()
    errors: list[str] = []
    events.listen("agent.error", lambda e: errors.append(e.get("agent")))
    orchestrator = Orchestrator(name="lead", instructions="route", events=events, fallbacks=["backup"])
    orchestrator.add_specialist(ExplodingAgent(), name="flaky", tool_name="flaky")
    orchestrator.add_specialist(EchoAgent(output="backup"), name="backup", tool_name="backup")
    reply = await orchestrator.invoke(Ctx(), "flaky", "x")
    assert reply == "backup:x"
    assert errors == ["flaky"]


async def test_orchestrator_unknown_agent_is_tool_safe():
    orchestrator = Orchestrator(name="lead", instructions="route")
    assert "unknown agent" in await orchestrator.invoke(Ctx(), "ghost", "x")


def test_supervisor_alias_builds_roster():
    supervisor = Supervisor({"writer": EchoAgent(), "researcher": EchoAgent()}, name="lead")
    tools = set(supervisor.agent._function_toolset.tools.keys())
    assert {"writer", "researcher"} <= tools
    assert supervisor.registry.names() == ["researcher", "writer"]


async def test_run_all_agents_uses_registry():
    registry_agents = {"a": EchoAgent("A"), "b": EchoAgent("B")}
    results = await run_all_agents(registry_agents, "task")
    assert results == {"a": "A:task", "b": "B:task"}


def test_registry_can_hold_remote_handle():
    registry = AgentRegistry()
    registry.register(AgentHandle.remote("peer", "http://peer"))
    assert registry.get("peer").is_remote is True
