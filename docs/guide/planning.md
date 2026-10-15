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
