# Tasks & Todos

## Who this page is for

No AI or agent experience is assumed. If you have ever written a to-do list to
get through a big project, you already understand the core idea of this page.

## The idea in one paragraph

Large language models are good at *one step at a time* but can lose the thread on
long, multi-step jobs ("research these five competitors, compare them, then write
a summary"). Humans solve this the same way a checklist does: write down the
steps, tick them off, and look back at the list when you lose focus. This page
gives your agent that checklist.

An **agent**, if you are new, is a program that sends instructions to a language
model and lets it call functions (**tools**) to get work done. A **tool** is just
a Python function the model is allowed to call — like "add a note" or "search the
web". We are about to add five such tools for managing a to-do list.

## Why a to-do list helps an agent

| Without a checklist | With a checklist |
| --- | --- |
| The model may forget step 3 by the time it reaches step 5 | Steps live outside the model, so they survive |
| You cannot tell *where* it got stuck | You can read the list: what's done, what's next |
| Long tasks drift | Each turn re-reads the list and continues |
| Resuming after an interruption is guesswork | The list is the plan; keep going from it |

::: tip It is just text the model reads
A "todo" is nothing more than a sentence the agent wrote down. The tools let it
write, read, and update those sentences. There is no magic — the value is that
the model *re-reads* its own plan.
:::

## Quickstart

Add the to-do tools to an agent and build it:

```python
from agentkit import AgentDefinition

class Planner(AgentDefinition):
    name = "planner"
    instructions = (
        "You are a careful assistant. For any multi-step task, first write a "
        "short checklist with write_todos, then work through it, marking items "
        "in_progress and completed as you go."
    )
    todos = True      # <-- adds write_todos/read_todos/add_todo/update_todo/clear_todos
    output = str

agent = Planner.build()
```

Fluent equivalent:

```python
from agentkit import Agent

agent = (
    Agent.make("planner")
    .instructions(
        "You are a careful assistant. For any multi-step task, first write a "
        "short checklist with write_todos, then work through it, marking items "
        "in_progress and completed as you go."
    )
    .todos()
    .output(str)
    .build()
)
```

That is the whole feature. When you run the agent, it can now manage a checklist.

The `todos = True` class field (or its fluent shortcut `.todos()`) is the same as:

```python
from agentkit.tasks import attach_tasks

attach_tasks(agent)
```

`.full()` also turns the `todos` layer on by default (pass `todos=False` to opt
out).

## The five tools

`attach_tasks` registers these tools. "Registering a tool" means the model can see
its name, what it does, and its inputs, and choose to call it.

| Tool | What the model uses it for | Example call |
| --- | --- | --- |
| `write_todos(todos)` | Replace the checklist with a fresh set of steps | `write_todos(["research", "compare", "summarize"])` |
| `read_todos()` | Re-read the checklist before deciding the next step | `read_todos()` |
| `add_todo(text)` | Append one more step you discovered later | `add_todo("cite sources")` |
| `update_todo(id, status)` | Mark a step `pending` / `in_progress` / `completed` | `update_todo(2, "completed")` |
| `clear_todos()` | Remove every step (start fresh) | `clear_todos()` |

A typical run looks like this from the outside:

```text
model: write_todos(["find sources", "compare", "write summary"])
model: update_todo(1, "in_progress")
model: update_todo(1, "completed"); update_todo(2, "in_progress")
...
model: <final answer>
```

You do not write that loop; the model does, guided by your instructions.

## Where the list is stored

The list lives in a **store**. `App` puts one in the run context automatically, so
the agent always finds it:

```python
# what happens under the hood, per app:
deps.extras["task_store"] = app.manager(DriverKind.TASKS).driver()
```

The default store keeps todos **in memory for the life of the app** — perfect for
one process. If you run several copies of your agent, or want todos to survive a
restart, choose a different store.

## Choosing a store (drivers)

This is the same "swap the implementation" idea from
[Contracts & Drivers](/guide/drivers). Select the store with `TASKS_DRIVER`
(default `memory`):

```bash
TASKS_DRIVER=memory        # the default
```

Or register your own — a store only needs five methods (`write`, `read`, `add`,
`update`, `clear`):

```python
from agentkit import DriverKind

app.extend(DriverKind.TASKS, "redis", lambda app: RedisTaskStore(app.settings.redis_url))
```

```bash
TASKS_DRIVER=redis
```

## Turning a goal into steps (planning strategies)

A **planning strategy** answers "given a goal, what are the steps?". Select it
with `PLANNING_DRIVER`:

| Driver | Behavior | Example |
| --- | --- | --- |
| `single` (default) | the goal is a single step | `"write a poem"` → `["write a poem"]` |
| `batched` | split on newlines/semicolons | `"a; b; c"` → `["a", "b", "c"]` |

```python
from agentkit import DriverKind

steps = await app.manager(DriverKind.PLANNING).driver("batched").plan("draft; edit; publish")
assert steps == ["draft", "edit", "publish"]
```

When you want the **model itself** to decompose the goal and run each step, use
the fuller [`Planner`](/guide/planning) instead.

## A complete, runnable example

```python
from agentkit import AgentDefinition, App, DriverKind

app = App("planner")

class Planner(AgentDefinition):
    name = "planner"
    instructions = "Break multi-step work into todos, then work the list."
    todos = True
    output = str

agent = Planner.build()

# Inspect the store directly (the agent does this for you during a run):
import asyncio

async def demo():
    store = app.manager(DriverKind.TASKS).driver()
    await store.write([{"text": "find sources"}, {"text": "compare"}])
    await store.update(1, status="completed")
    for todo in await store.read():
        print(todo)          # {'id': 1, 'text': 'find sources', 'status': 'completed'} ...

asyncio.run(demo())
```

## Testing

You can assert the tools were registered without running a real model:

```python
from agentkit import AgentDefinition

def test_tools_present():
    class T(AgentDefinition):
        name = "t"
        instructions = "x"
        todos = True
        output = str

    agent = T.build()
    tools = set(agent._function_toolset.tools)
    assert {"write_todos", "read_todos", "add_todo", "update_todo", "clear_todos"} <= tools
```

And exercise behavior with a stub store (no model needed):

```python
from types import SimpleNamespace
from agentkit.tasks import InMemoryTaskStore

async def test_add_todo():
    store = InMemoryTaskStore()
    todo = await store.add("write tests")
    assert todo["text"] == "write tests"
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| The model never writes todos | strengthen the instruction ("first write a checklist with write_todos") |
| Todos vanish between runs | the default store is in-memory; configure a durable `TASKS_DRIVER` |
| `unknown tasks driver` | the name is not registered — check spelling or `app.extend(...)` |
