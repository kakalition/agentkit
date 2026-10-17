from __future__ import annotations

from agentkit import END, Deps, StateGraph, Supervisor
from agentkit.foundation.agent import Agent
from agentkit.graph import GraphError
from agentkit.planning import Planner, parse_plan
from agentkit.teams import spawn_tool


class _Result:
    def __init__(self, output: str) -> None:
        self.output = output


class _StubAgent:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    async def run(self, prompt, *, deps=None, model=None, usage=None, **kwargs):  # noqa: ANN001
        self.prompts.append(prompt)
        return _Result(self.outputs.pop(0) if self.outputs else "")


def test_parse_plan_json_and_fallback():
    plan = parse_plan("ship it", '["a", "b", "c"]')
    assert [step.description for step in plan.steps] == ["a", "b", "c"]
    fenced = parse_plan("ship it", 'here you go: ["x", "y"] done')
    assert [step.description for step in fenced.steps] == ["x", "y"]
    listed = parse_plan("g", "1. one\n2. two\n- three")
    assert [step.description for step in listed.steps] == ["one", "two", "three"]


async def test_planner_executes_steps():
    agent = _StubAgent(['["step one", "step two"]', "result one", "result two"])
    planner = Planner(agent)
    plan = await planner.execute("do the thing")
    assert [step.result for step in plan.steps] == ["result one", "result two"]
    assert plan.done
    assert len(agent.prompts) == 3


async def test_state_graph_linear_and_conditional():
    async def start(state):
        return {"value": 1}

    async def double(state):
        return {"value": state["value"] * 2}

    def route(state):
        return "double" if state["value"] < 4 else END

    graph = StateGraph()
    graph.add_node("start", start)
    graph.add_node("double", double)
    graph.add_edge("start", "double")
    graph.add_conditional_edges("double", route)
    graph.set_entry("start")
    state = await graph.run({"value": 0})
    assert state["value"] == 4


async def test_state_graph_requires_entry():
    graph = StateGraph()
    try:
        await graph.run({})
    except GraphError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected GraphError")


def test_supervisor_builds_delegation_tools():
    import asyncio

    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    writer = Agent.make("writer").instructions("w").output(str).build()
    researcher = Agent.make("researcher").instructions("r").output(str).build()
    supervisor = Supervisor({"writer": writer, "researcher": researcher}, name="lead")
    agent = supervisor.build()
    tools = set(agent._function_toolset.tools.keys())
    assert {"writer", "researcher"} <= tools
    assert asyncio.run(agent.run("hi", model=FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])))).output == "ok"


async def test_spawn_tool_runs_sub_agent():
    sub = _StubAgent(["sub result"])
    tool = spawn_tool({"researcher": sub})

    class Ctx:
        deps = Deps(settings=None)
        usage = None

    out = await tool(Ctx(), "researcher", "find x")
    assert out == "sub result"
    assert (await tool(Ctx(), "nope", "x")).startswith("unknown agent")
