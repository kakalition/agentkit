# Planning & Graphs

## Introduction

Two tools for multi-step work: a **Planner** that decomposes a goal and executes
the steps, and a **StateGraph** for deterministic, branching pipelines.

## Plan-and-execute

`Planner` wraps an agent. It asks the agent to break a goal into ordered steps,
then runs each step, feeding prior results back as context.

```python
from agentkit.planning import Planner

planner = Planner(agent, max_steps=8)
run = await planner.execute("Prepare the quarterly report", deps=deps, model=model)

for step in run.steps:
    print(f"- {step.description}\n  → {step.result}")
print("done:", run.done)
```

Plan only, without executing:

```python
plan = await planner.plan("Prepare the quarterly report")
for step in plan.steps:
    print(step.description)
```

### The objects

```python
@dataclass
class PlanStep:
    description: str
    result: str = ""
    done: bool = False

@dataclass
class Plan:
    goal: str
    steps: list[PlanStep]
    @property
    def done(self) -> bool: ...
```

### Parsing

Plans are parsed leniently — JSON arrays, JSON objects with `steps`, or numbered /
bulleted lists all work:

```python
from agentkit.planning import parse_plan

parse_plan("goal", '["a", "b", "c"]')
parse_plan("goal", "1. a\n2. b")
```

### Step callbacks

```python
def on_step(step, plan):
    print(f"[{sum(s.done for s in plan.steps)}/{len(plan.steps)}] {step.description}")

planner = Planner(agent, on_step=on_step)
```

## State graphs

For deterministic pipelines — retrieve → draft → review → publish — use a
`StateGraph`. Nodes transform a state object; edges (or a router) choose what runs
next.

```python
from agentkit import StateGraph, END

async def retrieve(state):
    return {"docs": search(state["query"])}

def draft(state):
    return {"draft": write(state["docs"])}

def review(state):
    state["approved"] = len(state["draft"]) < 500
    return state

def route(state):
    return "publish" if state["approved"] else "draft"

graph = StateGraph()
graph.add_node("retrieve", retrieve)
graph.add_node("draft", draft)
graph.add_node("review", review)
graph.add_node("publish", lambda s: {**s, "done": True})

graph.add_edge("retrieve", "draft")
graph.add_edge("draft", "review")
graph.add_conditional_edges("review", route)
graph.add_edge("publish", END)

graph.set_entry("retrieve")
state = await graph.run({"query": "Q4 revenue"})
```

### Nodes, edges, state

- **Nodes** are `state -> state | partial_dict | None`. Return a dict to merge into
  the state, or mutate in place and return `None`.
- **Edges** (`add_edge`) are unconditional.
- **Routers** (`add_conditional_edges`) choose the next node from the state — return
  a node name or `END`.
- Cycles are allowed; a `max_steps` guard (default 100) prevents infinite loops.

### Errors

A missing entry, an unknown node, a missing outgoing edge, or exceeding
`max_steps` raises `GraphError`:

```python
from agentkit.graph import GraphError, END
```

## Planning vs. graphs

| Use | For |
| --- | --- |
| **Planner** | open-ended goals where the model should decide the steps |
| **StateGraph** | fixed pipelines with branches you control |

They compose: a graph node can run a `Planner`, and a plan step can call an agent
that itself uses specialists.

Continue to [Multi-Agent Teams →](/guide/teams)

## Graph executors and planning strategies

### What this is

A **state graph** is simply a flowchart for an agent's work. The boxes are
**nodes** (one step each), and the arrows are **edges** that say which step comes
next. A single object called the **state** — usually a dictionary — travels from
box to box; each node reads it and writes back whatever it produced, so the next
node can build on it. **Checkpointing** means saving a snapshot of that state
after each box, so a long run can be inspected or resumed from the last good step
instead of starting over.

The **graph executor** is the driver that decides *how* the flowchart runs:
strictly one box at a time, several independent boxes at once, or one box at a
time while saving a snapshot each step. Planning has its own small driver that
decides how a goal is broken into an ordered list of steps.

Think of a restaurant pass. A ticket (the state) moves station to station (grill →
plating → expo). You can move one ticket at a time (**sequential**), run two
independent stations in parallel (**parallel**), or photograph the ticket after
each station so a dropped plate can be remade from the last good state
(**checkpointed**).

### End-to-end example

```python
from agentkit import App, DriverKind, END, StateGraph

app = App(name="writer")

graph = StateGraph()                 # build the flowchart once
graph.add_node("retrieve", retrieve) # each node: state -> state | dict
graph.add_node("draft", draft)
graph.add_edge("retrieve", "draft")  # arrows between the boxes
graph.add_edge("draft", END)
graph.set_entry("retrieve")

# Default: GRAPH_DRIVER unset -> "sequential"; nodes run one at a time, in order.
state = await app.graph_executor.run(graph, {"query": "Q4 revenue"})

# Switch driver explicitly:
checkpointed = app.manager(DriverKind.GRAPH).driver("checkpointed")
await checkpointed.run(graph, {"query": "Q4 revenue"})    # snapshot after each node

# "parallel" instead fans out named nodes and merges their partial results (a join):
parallel = app.manager(DriverKind.GRAPH).driver("parallel")
await parallel.run(graph, {"query": "Q4 revenue"}, fan_out=["retrieve", "draft"])
```

### Drivers

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `sequential` | Runs one node at a time, following each edge in turn. This is the plain `StateGraph.run`. | Default. Pick it for the usual linear pipeline, retrieve → draft → review → publish. |
| `parallel` | Fan-out: runs the node names you pass in `fan_out=[...]` at the same time, each on its own copy of the state, then merges their partial results back into one state. Without `fan_out` it falls back to sequential. | Pick it when several nodes are independent and can overlap to cut latency. The nodes must not depend on each other's writes. |
| `checkpointed` | Runs nodes one at a time and stores a snapshot of the state after every node (in-process, under `executor.checkpoints`). | Pick it when you want to inspect intermediate state or resume from the last good node after a failure. |
| `single` | The planning strategy: treats the whole objective as a single step. | Default `PLANNING_DRIVER`. Pick it when the goal is already one clear instruction. |
| `batched` | The planning strategy: splits the objective on newlines and semicolons into several steps. | Pick it when you already supply a multi-line objective and want it divided into steps deterministically. |

The two "sides" of this page map to two driver kinds: `StateGraph` uses kind
`graph`, and the planning strategy uses kind `planning`.

### Selecting a driver

- **Setting** — one line in the environment or `.env`: `GRAPH_DRIVER=checkpointed`
  or `PLANNING_DRIVER=batched`.
- **Precedence** — an explicit name passed in code wins, then the setting, then
  the default (`sequential` for graphs, `single` for planning).
- **Per app** — `app.extend(DriverKind.GRAPH, "staged", lambda app: MyGraphExecutor())`.
- **Accessors** — `app.graph_executor` and `app.planning` return the configured
  drivers.
- **Reusable** — ship one for everyone with `@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.GRAPH, "staged")
def _staged_executor(app):
    return MyGraphExecutor()        # any object with async run(graph, state, **options)
```

Then select it with `GRAPH_DRIVER=staged`. See
[Contracts & Drivers](/guide/drivers) and [Tasks & Todos](/guide/tasks).

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `GraphError: no entry node set` | you never called `graph.set_entry(...)`. |
| `GraphError: node 'x' has no outgoing edge` | add `graph.add_edge("x", ...)` or `graph.add_conditional_edges("x", ...)`. |
| `GraphError: graph exceeded 100 steps (cycle?)` | a cycle never reaches `END`; fix the router or raise `max_steps`. |
| A `parallel` run behaves sequentially | no `fan_out=[...]` node names were passed, so it fell back to sequential. |
| Checkpoints are empty after a run | checkpoints live on the executor instance; read them from the same `app.graph_executor` you ran (or keep your own reference). |
| `unknown graph driver` / `unknown planning driver` | the `GRAPH_DRIVER`/`PLANNING_DRIVER` value is misspelled or not registered; fix it or `app.extend(...)` it. |
