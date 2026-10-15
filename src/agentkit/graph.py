"""A small async state-graph workflow engine, backed by ``pydantic-graph``.

Nodes are ``state -> state | None`` callables run in order along edges; a router
selects the next node from state. Useful for deterministic multi-step pipelines
(retrieve → draft → review → publish) and agent graphs::

    from agentkit.graph import END, StateGraph

    graph = StateGraph()
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", END)
    graph.set_entry("retrieve")
    state = await graph.run({"query": "…"})

State is a mutable mapping (e.g. a ``dict``); nodes may return a partial dict to
merge, or mutate in place and return ``None``.

Execution is compiled to a :mod:`pydantic_graph` graph (typed start/step/decision
nodes) so it shares PydanticAI's durable-execution path; :meth:`StateGraph.
to_pydantic_graph` exposes the compiled graph directly. State that is not a
mutable mapping falls back to a built-in async loop.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from pydantic_graph import GraphBuilder

__all__ = ["END", "StateGraph", "GraphError"]

END = "__end__"
NodeFn = Callable[[Any], Any]
RouterFn = Callable[[Any], str]


class GraphError(RuntimeError):
    pass


class StateGraph:
    """An ordered async state machine over a mutable state object."""

    def __init__(self, *, max_steps: int = 100) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._routers: dict[str, RouterFn] = {}
        self._entry: str | None = None
        self.max_steps = max_steps

    # -- construction ---------------------------------------------------
    def add_node(self, name: str, function: NodeFn) -> StateGraph:
        self._nodes[name] = function
        return self

    def add_edge(self, source: str, target: str) -> StateGraph:
        self._edges[source] = target
        return self

    def add_conditional_edges(self, source: str, router: RouterFn) -> StateGraph:
        self._routers[source] = router
        return self

    def set_entry(self, name: str) -> StateGraph:
        self._entry = name
        return self

    # -- run ------------------------------------------------------------
    async def run(self, state: Any) -> Any:
        if self._entry is None:
            raise GraphError("no entry node set")
        if self._entry not in self._nodes:
            raise GraphError(f"unknown node: {self._entry}")
        self._validate()
        if isinstance(state, MutableMapping):
            return await self._run_graph(state)
        return await self._run_internal(state)  # pragma: no cover - non-mapping state

    def _validate(self) -> None:
        for name in self._nodes:
            router = self._routers.get(name)
            if router is not None:
                continue
            edge = self._edges.get(name)
            if edge is None:
                raise GraphError(f"node {name!r} has no outgoing edge")
            if edge != END and edge not in self._nodes:
                raise GraphError(f"unknown node: {edge}")

    # -- pydantic-graph compilation -------------------------------------
    def to_pydantic_graph(self, *, name: str = "state_graph") -> Any:
        """Compile to a :class:`pydantic_graph.Graph` (durable-execution ready)."""
        if self._entry is None:
            raise GraphError("no entry node set")
        builder = GraphBuilder(
            name=name, state_type=dict, input_type=dict, output_type=dict
        )
        counter = [0]

        def record_step() -> None:
            counter[0] += 1
            if counter[0] > self.max_steps:
                raise GraphError(f"graph exceeded {self.max_steps} steps (cycle?)")

        steps: dict[str, Any] = {}
        for node_name, function in self._nodes.items():
            steps[node_name] = builder.step(
                self._make_step(function, record_step), node_id=node_name
            )

        for node_name in self._nodes:
            router = self._routers.get(node_name)
            if router is not None:
                route_step = builder.step(
                    self._make_router_step(router, record_step), node_id=f"{node_name}__route"
                )
                decision = builder.decision(node_id=f"{node_name}__decision")
                targets = [*self._nodes, END]
                for target in targets:
                    destination = (
                        builder.end_node if target == END else steps[target]
                    )
                    decision = decision.branch(
                        builder.match(str, matches=self._matcher(target)).to(destination)
                    )
                builder.add_edge(steps[node_name], route_step)
                builder.add_edge(route_step, decision)
            else:
                target = self._edges[node_name]
                destination = builder.end_node if target == END else steps[target]
                builder.add_edge(steps[node_name], destination)

        builder.add_edge(builder.start_node, steps[self._entry])
        return builder.build()

    @staticmethod
    def _matcher(target: str) -> Callable[[Any], bool]:
        def matches(value: Any) -> bool:
            return value == target

        return matches

    def _make_step(self, function: NodeFn, record_step: Callable[[], None]) -> Any:
        async def step(ctx: Any) -> None:
            record_step()
            result = function(ctx.state)
            if inspect.isawaitable(result):
                result = await result
            _merge_into(ctx.state, result)

        return step

    def _make_router_step(self, router: RouterFn, record_step: Callable[[], None]) -> Any:
        async def step(ctx: Any) -> str:
            record_step()
            target = router(ctx.state)
            if inspect.isawaitable(target):
                target = await target
            if target not in self._nodes and target != END:
                raise GraphError(f"router from {ctx.node_id!r} chose unknown node {target!r}")
            return target

        return step

    async def _run_graph(self, state: Any) -> Any:
        graph = self.to_pydantic_graph()
        await graph.run(state=state, inputs={})
        return state

    # -- built-in fallback ----------------------------------------------
    async def _run_internal(self, state: Any) -> Any:
        current = self._entry
        steps = 0
        while current != END:
            steps += 1
            if steps > self.max_steps:
                raise GraphError(f"graph exceeded {self.max_steps} steps (cycle?)")
            node = self._nodes.get(current)  # type: ignore[arg-type]
            if node is None:
                raise GraphError(f"unknown node: {current}")
            result = node(state)
            if inspect.isawaitable(result):
                result = await result
            state = _merge(state, result)
            current = self._next(current, state)  # type: ignore[arg-type]
        return state

    def _next(self, current: str, state: Any) -> str:
        router = self._routers.get(current)
        if router is not None:
            target = router(state)
            if target not in self._nodes and target != END:
                raise GraphError(f"router from {current!r} chose unknown node {target!r}")
            return target
        edge = self._edges.get(current)
        if edge is None:
            raise GraphError(f"node {current!r} has no outgoing edge")
        return edge


def _merge_into(state: Any, result: Any) -> None:
    if result is None:
        return
    if isinstance(state, MutableMapping) and isinstance(result, Mapping):
        state.update(result)
    else:  # pragma: no cover - non-mapping state
        raise GraphError("non-mapping state cannot be replaced in pydantic-graph mode")


def _merge(state: Any, result: Any) -> Any:
    if result is None:
        return state
    if isinstance(state, dict) and isinstance(result, Mapping):
        merged = dict(state)
        merged.update(result)
        return merged
    return result
