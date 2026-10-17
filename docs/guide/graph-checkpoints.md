# Graph Interrupts & Checkpoints

`StateGraph` runs nodes in order. A node can **pause** the graph to wait for
external input (a human approval, a fetched value) and the run continues later
from a persisted checkpoint.

## Pausing a node

Call `interrupt(payload)` inside a node. The first time it raises a pause; on
resume the same call returns the value you supply:

```python
from agentkit import END, StateGraph, interrupt


async def ask(state):
    decision = interrupt({"question": "approve this draft?"})
    return {"decision": decision}


async def publish(state):
    return {"published": state["decision"] == "yes"}


graph = StateGraph()
graph.add_node("ask", ask)
graph.add_node("publish", publish)
graph.add_edge("ask", "publish")
graph.add_edge("publish", END)
graph.set_entry("ask")
```

## Running and resuming

Pass a `CheckpointStore` (and an optional `run_id`) so node boundaries are saved:

```python
from agentkit import MemoryCheckpointStore

store = MemoryCheckpointStore()
result = await graph.run({"draft": "…"}, run_id="job-1", checkpointer=store)
# result is an Interrupt(node="ask", payload={"question": …})

final = await graph.resume("job-1", "yes", checkpointer=store)
# {"draft": "…", "decision": "yes", "published": True}
```

A node may interrupt more than once; each `resume` answers the next pause. Load a
specific snapshot with `resume(..., seq=...)`. Without a checkpointer, `run` still
returns an `Interrupt`, but there is nothing to resume from.

`run_durable(...)` is the documented durable entry point; `run(...)` is an alias
that delegates to it, so there is one implementation.

## Scope & limits

Durable resume is **node-boundary only**: a checkpoint is saved after each node
completes, so an interrupt pauses at a node boundary and `resume` restarts from
there. There is no mid-node resume (DBOS does not expose the hook).

The compiled `to_pydantic_graph()` form is for pydantic-graph interop and is **not**
checkpointed — it has no interrupt/resume and does not persist state. Interrupt and
resume live in agentkit's `StateGraph` loop and persist through the same
`CheckpointStore` used elsewhere.
