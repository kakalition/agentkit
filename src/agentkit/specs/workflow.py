"""The ``workflow`` spec — a declarative state graph that materializes to ``StateGraph``.

    from agentkit.specs.workflow import WorkflowDefinition, WorkflowNode

    spec = WorkflowDefinition(
        name="pipeline",
        nodes=[WorkflowNode(name="retrieve"), WorkflowNode(name="draft")],
        edges={"retrieve": "draft", "draft": "__end__"},
        entry="retrieve",
    )
    graph = SPECS.materialize("workflow", spec, functions={"retrieve": r, "draft": d})
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from agentkit.graph import END
from agentkit.specs.base import SpecKind, SpecModel
from agentkit.specs.codegen import register_python_renderer
from agentkit.specs.registry import SPECS

__all__ = [
    "WorkflowDefinition",
    "WorkflowNode",
    "materialize_workflow",
    "render_workflow_code",
    "run_workflow",
]


class WorkflowNode(BaseModel):
    """One node: a named function, or a named agent referenced by ``agent``."""

    name: str
    kind: str = "function"  # function | agent | router
    description: str = ""
    agent: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("node name must not be empty")
        return value


class WorkflowDefinition(SpecModel):
    """A serializable workflow (nodes, edges, conditional routers, entry point)."""

    spec_kind = SpecKind.WORKFLOW

    name: str
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: dict[str, str] = Field(default_factory=dict)
    routers: dict[str, str] = Field(default_factory=dict)
    entry: str = ""
    state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("workflow name must not be empty")
        return value

    @model_validator(mode="after")
    def _valid_graph(self) -> WorkflowDefinition:
        names = {node.name for node in self.nodes}
        if self.entry and self.entry not in names:
            raise ValueError(f"entry {self.entry!r} is not a node")
        for source, target in self.edges.items():
            if source not in names:
                raise ValueError(f"edge source {source!r} is not a node")
            if target != END and target not in names:
                raise ValueError(f"edge target {target!r} is not a node")
        for source in self.routers:
            if source not in names:
                raise ValueError(f"router source {source!r} is not a node")
        return self


def _resolve_function(
    node: WorkflowNode,
    functions: Mapping[str, Any],
    agents: Mapping[str, Any],
) -> Any:
    if node.name in functions:
        return functions[node.name]
    if node.agent and node.agent in agents:
        handle = agents[node.agent]
        return _node_from_agent(handle)
    return _passthrough(node.name)


def _node_from_agent(handle: Any) -> Any:
    async def node(state: Any) -> Any:
        prompt = state.get("task") if isinstance(state, Mapping) else str(state)
        if hasattr(handle, "invoke"):
            output = await handle.invoke(None, prompt or "")
        else:
            result = handle.run(prompt or "")
            output = getattr(result, "output", result)
        return {"task": prompt, "output": output, "last": node.__name__}

    return node


def _passthrough(name: str) -> Any:
    def node(state: Any) -> dict[str, Any]:
        return {"last": name}

    node.__name__ = name
    return node


def materialize_workflow(
    definition: WorkflowDefinition,
    *,
    functions: Mapping[str, Any] | None = None,
    agents: Mapping[str, Any] | None = None,
    routers: Mapping[str, Any] | None = None,
) -> Any:
    """Build a :class:`~agentkit.graph.StateGraph` from a workflow spec."""
    from agentkit.graph import StateGraph

    functions = functions or {}
    agents = agents or {}
    routers = routers or {}
    graph = StateGraph()
    for node in definition.nodes:
        graph.add_node(node.name, _resolve_function(node, functions, agents))
    for source, target in definition.edges.items():
        graph.add_edge(source, target)
    for source, router_name in definition.routers.items():
        router = routers.get(router_name)
        if router is not None:
            graph.add_conditional_edges(source, router)
    graph.set_entry(definition.entry or (definition.nodes[0].name if definition.nodes else ""))
    return graph


async def run_workflow(
    definition: WorkflowDefinition,
    prompt: str = "",
    *,
    state: dict[str, Any] | None = None,
    functions: Mapping[str, Any] | None = None,
    agents: Mapping[str, Any] | None = None,
    routers: Mapping[str, Any] | None = None,
    executor: Any = None,
) -> dict[str, Any]:
    """Materialize a workflow spec and run it end-to-end (returns the final state)."""
    graph = materialize_workflow(definition, functions=functions, agents=agents, routers=routers)
    initial = dict(state) if state is not None else dict(definition.state)
    if prompt:
        initial.setdefault("task", prompt)
    if executor is not None:
        final = await executor.run(graph, initial)
    else:
        final = await graph.run(initial)
    return {"workflow": definition.name, "state": final}


def render_workflow_code(definition: WorkflowDefinition) -> str:
    """Generate the Python that rebuilds a workflow definition."""
    lines = [
        f"# Generated by agentkit Studio — workflow {definition.name!r}",
        "from agentkit.graph import END, StateGraph",
        "",
        "graph = StateGraph()",
    ]
    for node in definition.nodes:
        lines.append(f'graph.add_node({node.name!r}, {node.name})  # wire the {node.name!r} callable')
    for source, target in definition.edges.items():
        expr = "END" if target == END else repr(target)
        lines.append(f"graph.add_edge({source!r}, {expr})")
    for source, router in definition.routers.items():
        lines.append(f"graph.add_conditional_edges({source!r}, {router})")
    lines.append(f"graph.set_entry({(definition.entry or '')!r})")
    lines.append("state = await graph.run({})")
    return "\n".join(lines) + "\n"


SPECS.register(
    SpecKind.WORKFLOW,
    WorkflowDefinition,
    materializer=materialize_workflow,
    runner=run_workflow,
)
register_python_renderer(SpecKind.WORKFLOW, render_workflow_code)
