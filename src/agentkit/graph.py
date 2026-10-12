"""A small async state-graph workflow engine.

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

State is a mutable mapping (e.g. a ``dict`` or a dataclass); nodes may return a
partial dict to merge, or mutate in place and return ``None``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

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
        current = self._entry
        steps = 0
        while current != END:
            steps += 1
            if steps > self.max_steps:
                raise GraphError(f"graph exceeded {self.max_steps} steps (cycle?)")
            node = self._nodes.get(current)
            if node is None:
                raise GraphError(f"unknown node: {current}")
            result = node(state)
            if inspect.isawaitable(result):
                result = await result
            state = _merge(state, result)
            current = self._next(current, state)
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

def _merge(state: Any, result: Any) -> Any:
    if result is None:
        return state
    if isinstance(state, dict) and isinstance(result, Mapping):
        merged = dict(state)
        merged.update(result)
        return merged
    return result
