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

Execution runs through agentkit's own node loop, which persists node-boundary
checkpoints (and supports :func:`interrupt`/:meth:`StateGraph.resume`) when a
checkpointer is supplied — see :meth:`StateGraph.run_durable`. :meth:`StateGraph.
to_pydantic_graph` compiles the same graph to a :mod:`pydantic_graph` graph for
interop; that compiled graph is **not** checkpointed. State that is not a mutable
mapping falls back to the built-in async loop.
"""

from __future__ import annotations

import contextlib
import copy
import inspect
from collections.abc import Callable, Mapping, MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic_graph import GraphBuilder

from agentkit.contracts.graph import GraphExecutor
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, GraphDriver
from agentkit.support.manager import Manager

__all__ = [
    "END",
    "CheckpointedGraphExecutor",
    "GraphError",
    "GraphExecutor",
    "GraphInterrupt",
    "GraphManager",
    "Interrupt",
    "ParallelGraphExecutor",
    "SequentialGraphExecutor",
    "StateGraph",
    "interrupt",
]

END = "__end__"
NodeFn = Callable[[Any], Any]
RouterFn = Callable[[Any], str]


class GraphError(RuntimeError):
    pass


class GraphInterrupt(Exception):
    """Raised by :func:`interrupt` to pause a node and await external input."""

    def __init__(self, payload: Any = None, *, node: str | None = None) -> None:
        super().__init__("graph interrupted")
        self.payload = payload
        self.node = node


@dataclass
class Interrupt:
    """The result of a paused run — resume it with :meth:`StateGraph.resume`."""

    run_id: str
    node: str
    payload: Any = None
    state: Any = None
    seq: int | None = None


_current_node: ContextVar[str | None] = ContextVar("agentkit_graph_node", default=None)
_answers: ContextVar[list[Any] | None] = ContextVar("agentkit_graph_answers", default=None)
_answer_index: ContextVar[int] = ContextVar("agentkit_graph_answer_index", default=0)


def interrupt(payload: Any = None) -> Any:
    """Pause the running node; returns the value passed to :meth:`StateGraph.resume`.

    Call it inside a node: the first call pauses the graph (returning an
    :class:`Interrupt`); on resume the same call returns the supplied value. A node
    may call it repeatedly — each call is answered by a subsequent resume.
    """
    index = _answer_index.get()
    answers = _answers.get() or []
    if index < len(answers):
        _answer_index.set(index + 1)
        return answers[index]
    raise GraphInterrupt(payload, node=_current_node.get())


class StateGraph:
    """An ordered async state machine over a mutable state object."""

    def __init__(self, *, max_steps: int = 100) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._routers: dict[str, RouterFn] = {}
        self._entry: str | None = None
        self.max_steps = max_steps
        #: Default checkpoint store for :meth:`run`/:meth:`resume` (if any).
        self.checkpointer: Any = None

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

    # -- specs ----------------------------------------------------------
    def to_spec(self, name: str = "workflow", **extra: Any) -> Any:
        """Describe this graph as a :class:`~agentkit.specs.workflow.WorkflowDefinition`."""
        from agentkit.specs.workflow import WorkflowDefinition, WorkflowNode

        return WorkflowDefinition(
            name=name,
            nodes=[WorkflowNode(name=node) for node in self._nodes],
            edges=dict(self._edges),
            routers={source: f"{source}__router" for source in self._routers},
            entry=self._entry or "",
            **extra,
        )

    @classmethod
    def from_spec(cls, spec: Any, **options: Any) -> StateGraph:
        """Build a graph from a workflow spec (see ``specs.workflow.materialize_workflow``)."""
        from agentkit.specs.workflow import materialize_workflow

        return materialize_workflow(spec, **options)  # type: ignore[return-value]

    # -- run ------------------------------------------------------------
    async def run(
        self, state: Any, *, run_id: str | None = None, checkpointer: Any = None
    ) -> Any:
        """Run the graph (alias of :meth:`run_durable`).

        Pass ``run_id``/``checkpointer`` (or set ``self.checkpointer``) to persist
        node-boundary checkpoints so an interrupted run can be :meth:`resume`d.
        """
        return await self.run_durable(state, run_id=run_id, checkpointer=checkpointer)

    async def run_durable(
        self, state: Any, *, run_id: str | None = None, checkpointer: Any = None
    ) -> Any:
        """The durable entry point: run with node-boundary checkpointing.

        This is the documented way to run a graph with durable resume. With a
        ``checkpointer`` (or ``self.checkpointer``) every node boundary is saved, so
        a node that calls :func:`interrupt` pauses the run and :meth:`resume`
        continues it. Resume is node-boundary only — there is no mid-node resume
        (the compiled :mod:`pydantic_graph` form is not checkpointed either).
        """
        if self._entry is None:
            raise GraphError("no entry node set")
        if self._entry not in self._nodes:
            raise GraphError(f"unknown node: {self._entry}")
        self._validate()
        store = checkpointer if checkpointer is not None else self.checkpointer
        return await self._loop(
            state,
            run_id=run_id,
            checkpointer=store,
            start=self._entry,
            resume_answers=[],
        )

    async def resume(
        self, run_id: str, value: Any = None, *, checkpointer: Any = None, seq: int | None = None
    ) -> Any:
        """Continue a run paused at an :class:`Interrupt`, injecting ``value``.

        Loads the latest checkpoint, or the explicit ``seq`` when given.
        """
        store = checkpointer if checkpointer is not None else self.checkpointer
        if store is None:
            raise GraphError("resume requires a checkpointer")
        record = await store.get(run_id, seq) if seq is not None else await store.latest(run_id)
        if record is None:
            raise GraphError(f"unknown run_id: {run_id!r}")
        payload = getattr(record, "state", None)
        if not isinstance(payload, Mapping) or "next" not in payload or "state" not in payload:
            raise GraphError(f"run {run_id!r} has no resumable interrupt")
        record_seq = int(getattr(record, "seq", 0) or 0)
        answers = list(payload.get("answers") or [])
        answers.append(value)
        return await self._loop(
            payload["state"],
            run_id=run_id,
            checkpointer=store,
            start=payload["next"],
            resume_answers=answers,
            start_seq=record_seq + 1,
        )

    async def _loop(
        self,
        state: Any,
        *,
        run_id: str | None,
        checkpointer: Any,
        start: str,
        resume_answers: list[Any],
        start_seq: int = 0,
        on_step: Callable[[str, Any], Any] | None = None,
    ) -> Any:
        resolved_run_id = run_id or f"graph:{uuid4().hex}"
        current: str = start
        steps = 0
        seq = start_seq
        node_token = _current_node.set(current)
        answers_token = _answers.set(list(resume_answers))
        index_token = _answer_index.set(0)
        try:
            while current != END:
                steps += 1
                if steps > self.max_steps:
                    raise GraphError(f"graph exceeded {self.max_steps} steps (cycle?)")
                node = self._nodes.get(current)
                if node is None:
                    raise GraphError(f"unknown node: {current}")
                _current_node.set(current)
                try:
                    result = node(state)
                    if inspect.isawaitable(result):
                        result = await result
                except GraphInterrupt as pause:
                    pending = pause.node or current
                    await self._save(
                        checkpointer,
                        resolved_run_id,
                        seq,
                        state,
                        pending,
                        list(_answers.get() or []),
                    )
                    return Interrupt(
                        run_id=resolved_run_id,
                        node=pending,
                        payload=pause.payload,
                        state=copy.deepcopy(state),
                        seq=seq,
                    )
                state = _merge(state, result)
                if on_step is not None:
                    outcome = on_step(current, state)
                    if inspect.isawaitable(outcome):
                        await outcome
                current = self._next(current, state)  # type: ignore[arg-type]
                if checkpointer is not None:
                    await self._save(checkpointer, resolved_run_id, seq, state, current, [])
                    seq += 1
            return state
        finally:
            _current_node.reset(node_token)
            _answers.reset(answers_token)
            _answer_index.reset(index_token)

    async def _save(
        self,
        store: Any,
        run_id: str,
        seq: int,
        state: Any,
        next_node: str,
        answers: list[Any],
    ) -> None:
        if store is None:
            return
        with contextlib.suppress(Exception):  # a checkpoint must never break the run
            await store.put(
                run_id,
                seq,
                {"state": copy.deepcopy(state), "next": next_node, "answers": list(answers)},
                label=next_node,
            )

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
        """Compile to a :class:`pydantic_graph.Graph` for interop.

        The compiled graph is a plain :mod:`pydantic_graph` graph: useful for
        interop with PydanticAI, but it is **not** checkpointed and does not
        support :func:`interrupt`/:meth:`resume`. Use :meth:`run_durable` for
        durable execution.
        """
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

    # -- built-in loop --------------------------------------------------
    async def run_steps(self, state: Any, *, on_step: Callable[[str, Any], Any] | None = None) -> Any:
        """Run the node loop, optionally invoking ``on_step(node_name, state)`` after each."""
        if self._entry is None:
            raise GraphError("no entry node set")
        self._validate()
        return await self._loop(
            state,
            run_id=None,
            checkpointer=None,
            start=self._entry,
            resume_answers=[],
            on_step=on_step,
        )

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


class SequentialGraphExecutor:
    """The default graph executor: nodes run in order (``StateGraph.run``)."""

    async def run(self, graph: Any, state: Any, **options: Any) -> Any:
        return await graph.run(state)


class ParallelGraphExecutor:
    """Fan-out: run named nodes concurrently and merge their partial results.

    ``run(graph, state, fan_out=["a", "b"])`` runs ``a`` and ``b`` on copies of
    ``state`` at the same time and merges the results back (a join).
    """

    async def run(self, graph: Any, state: Any, **options: Any) -> Any:
        import asyncio

        names = list(options.get("fan_out") or [])
        if not names:
            return await graph.run(state)

        async def branch(name: str) -> Any:
            node = graph._nodes[name]
            local = copy.deepcopy(state)
            result = node(local)
            if inspect.isawaitable(result):
                result = await result
            return _merge(local, result)

        results = await asyncio.gather(*(branch(name) for name in names))
        merged = state
        for partial in results:
            if isinstance(merged, MutableMapping) and isinstance(partial, Mapping):
                merged.update(partial)
            else:  # pragma: no cover - non-mapping state
                merged = partial
        return merged


class CheckpointedGraphExecutor:
    """Records a state snapshot after every node.

    With a :class:`~agentkit.checkpoints.CheckpointStore` the snapshots persist
    (``store.put(run_id, seq, state, label=node)``) so a run can be inspected and
    resumed; without one they stay in the in-process ``checkpoints`` dict.
    """

    def __init__(self, store: Any = None, *, run_id: str = "run") -> None:
        self.checkpoints: dict[str, Any] = {}
        self.store = store
        self.run_id = run_id
        self._seq = 0

    async def run(self, graph: Any, state: Any, **options: Any) -> Any:
        store = options.get("store", self.store)
        run_id = options.get("run_id", self.run_id)

        async def save(node: str, current: Any) -> None:
            self.checkpoints[node] = copy.deepcopy(current)
            if store is not None:
                with contextlib.suppress(Exception):
                    await store.put(run_id, self._seq, copy.deepcopy(current), label=node)
                self._seq += 1

        return await graph.run_steps(state, on_step=save)


class GraphManager(Manager):
    """Resolves the configured graph executor (``graph_driver``, default ``sequential``)."""

    kind = DriverKind.GRAPH
    default_driver = GraphDriver.SEQUENTIAL


@register_driver(DriverKind.GRAPH, GraphDriver.SEQUENTIAL)
class SequentialGraphDriver(Driver):
    def build(self) -> SequentialGraphExecutor:
        return SequentialGraphExecutor()
@register_driver(DriverKind.GRAPH, GraphDriver.PARALLEL)
class ParallelGraphDriver(Driver):
    def build(self) -> ParallelGraphExecutor:
        return ParallelGraphExecutor()
@register_driver(DriverKind.GRAPH, GraphDriver.CHECKPOINTED)
class CheckpointedGraphDriver(Driver):
    def build(self) -> CheckpointedGraphExecutor:
        app = self.app
        store = None
        try:
            if bool(getattr(app.settings, "checkpoints_enabled", False)):
                store = app.manager("checkpoint").driver()
        except Exception:  # pragma: no cover - checkpoint store is best-effort
            store = None
        return CheckpointedGraphExecutor(store)
