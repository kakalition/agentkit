"""WS2.1 — graph interrupt / resume, persisted through a CheckpointStore."""

from __future__ import annotations

from typing import Any

import pytest

from agentkit.checkpoints import MemoryCheckpointStore
from agentkit.graph import END, GraphError, Interrupt, StateGraph, interrupt


def _gate_graph() -> StateGraph:
    async def ask(state: Any) -> Any:
        decision = interrupt({"question": "approve?"})
        return {"decision": decision}

    async def finish(state: Any) -> Any:
        return {"done": True, "decision": state.get("decision")}

    graph = StateGraph()
    graph.add_node("ask", ask)
    graph.add_node("finish", finish)
    graph.add_edge("ask", "finish")
    graph.add_edge("finish", END)
    graph.set_entry("ask")
    return graph


async def test_single_interrupt_and_resume() -> None:
    store = MemoryCheckpointStore()
    graph = _gate_graph()
    result = await graph.run({"n": 1}, run_id="r1", checkpointer=store)
    assert isinstance(result, Interrupt)
    assert result.node == "ask"
    assert result.payload == {"question": "approve?"}
    assert result.state == {"n": 1}

    final = await graph.resume("r1", "yes", checkpointer=store)
    assert final == {"n": 1, "decision": "yes", "done": True}


async def test_repeated_interrupts() -> None:
    async def two_questions(state: Any) -> Any:
        first = interrupt("first")
        second = interrupt("second")
        return {"first": first, "second": second}

    graph = StateGraph()
    graph.add_node("q", two_questions)
    graph.add_edge("q", END)
    graph.set_entry("q")

    store = MemoryCheckpointStore()
    paused = await graph.run({}, run_id="r2", checkpointer=store)
    assert isinstance(paused, Interrupt)
    assert paused.payload == "first"

    paused2 = await graph.resume("r2", "A", checkpointer=store)
    assert isinstance(paused2, Interrupt)
    assert paused2.payload == "second"

    final = await graph.resume("r2", "B", checkpointer=store)
    assert final == {"first": "A", "second": "B"}


async def test_resume_with_explicit_seq() -> None:
    store = MemoryCheckpointStore()
    graph = _gate_graph()
    await graph.run({}, run_id="r3", checkpointer=store)
    records = await store.list("r3")
    final = await graph.resume("r3", "ok", checkpointer=store, seq=records[-1].seq)
    assert final["decision"] == "ok"


async def test_unknown_run_id_raises() -> None:
    graph = _gate_graph()
    store = MemoryCheckpointStore()
    with pytest.raises(GraphError):
        await graph.resume("nope", "x", checkpointer=store)


async def test_default_path_unchanged_without_interrupts() -> None:
    async def start(state: Any) -> Any:
        return {"value": 1}

    async def double(state: Any) -> Any:
        return {"value": state["value"] * 2}

    def route(state: Any) -> str:
        return "double" if state["value"] < 4 else END

    graph = StateGraph()
    graph.add_node("start", start)
    graph.add_node("double", double)
    graph.add_edge("start", "double")
    graph.add_conditional_edges("double", route)
    graph.set_entry("start")
    assert (await graph.run({"value": 0}))["value"] == 4


async def test_resume_without_checkpointer_raises() -> None:
    graph = _gate_graph()
    with pytest.raises(GraphError):
        await graph.resume("r", "x")


async def test_run_durable_persists_checkpoints_and_resumes() -> None:
    store = MemoryCheckpointStore()
    graph = _gate_graph()
    paused = await graph.run_durable({"n": 1}, run_id="rd1", checkpointer=store)
    assert isinstance(paused, Interrupt)
    assert await store.list("rd1")  # node-boundary checkpoints were persisted
    final = await graph.resume("rd1", "yes", checkpointer=store)
    assert final == {"n": 1, "decision": "yes", "done": True}


async def test_compiled_graph_matches_run_result() -> None:
    async def start(state: Any) -> Any:
        return {"value": 1}

    async def double(state: Any) -> Any:
        return {"value": state["value"] * 2}

    def route(state: Any) -> str:
        return "double" if state["value"] < 4 else END

    graph = StateGraph()
    graph.add_node("start", start)
    graph.add_node("double", double)
    graph.add_edge("start", "double")
    graph.add_conditional_edges("double", route)
    graph.set_entry("start")

    expected = await graph.run({"value": 0})
    state = {"value": 0}
    # the compiled graph is not checkpointed; it mutates the shared state mapping
    await graph.to_pydantic_graph().run(state=state, inputs={})
    assert state == expected
