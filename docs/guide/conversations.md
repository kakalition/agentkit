# Conversations

A **conversation** is a durable, id-addressed thread of messages. Every turn
appends to it, so an agent resumes where it left off across restarts.

## Conversation ids

A conversation id is any string; by convention it is `"<channel>:<id>"`:

```python
await app.run("hello", conversation_id="cli:default")
await app.run("hi",    conversation_id="telegram:12345")
await app.run("write", conversation_id="a2a:task-7")
```

The prefix becomes the conversation's `channel`, which the operator UI groups by.

## The `ChatRunner`

`app.run(...)` is a convenience over `ChatRunner`, the object that actually drives
a turn:

```python
with app.repositories() as repos:
    runner = ChatRunner(
        app.deps(repos),
        agent=app.agent(),
        conversation_id="cli:default",
    )
    result = await runner.send("hello")
```

`ChatRunner.send` does the following, in order:

1. ensures the conversation exists;
2. loads recent history (bounded by `max_history`);
3. runs any [history processor](/guide/compaction);
4. emits `turn.start` and `channel.message`;
5. runs the agent with the history, model settings, and usage limits;
6. appends the new messages, touches the conversation, records usage;
7. emits `turn.end` and returns a `ChatResult`.

## `ChatResult`

```python
@dataclass
class ChatResult:
    output: str
    artifacts: list[dict]
    history_length: int
    usage: dict | None
    tool_calls: list[str]
```

- **`output`** — the model's final text.
- **`artifacts`** — files/tools' declared artifacts plus any generated media.
- **`usage`** — token counts and estimated `cost_usd`.
- **`tool_calls`** — the tool names invoked this turn (handy for [evaluations](/guide/evaluations)).

## History

History is persisted as serialized PydanticAI messages and reloaded per turn. The
default window is bounded (`DEFAULT_MAX_HISTORY`), and long threads are kept
coherent by [context compaction](/guide/compaction).

```python
from agentkit import load_history

with app.repositories() as repos:
    messages = load_history(repos, "cli:default", max_messages=40)
```

## Branching and replay

Copy a conversation to explore an alternative, or re-run the last user prompt:

```python
app.fork("cli:main", "cli:experiment")          # up to a branch point
app.fork("cli:main", "cli:experiment", upto=6)  # first 6 messages

result = await app.replay("cli:main")                    # into cli:main:replay
result = await app.replay("cli:main", target="cli:try2") # a named target
```

`replay` forks the conversation up to the last user message, then re-runs that
prompt — useful for A/B testing a new model, prompt, or tool set.

## Usage accounting

Every turn records tokens and an estimated cost (from `genai_prices`) against the
conversation:

```python
with app.repositories() as repos:
    totals = repos.usage.totals()                      # global
    rows = repos.usage.list(limit=50)                  # per-turn rows
```

`UsageRepo.totals()` returns `requests`, `input_tokens`, `output_tokens`,
`total_tokens`, and `cost_usd`. See [Model Routing & Cost](/guide/routing) and
[Budgets](/guide/budgets).

## The audit log

Sensitive actions can be recorded in a **hash-chained** audit log that is
verifiable:

```python
with app.repositories() as repos:
    repos.audit.append("note.created", target=f"note:{note.id}", actor="owner")

    assert repos.audit.verify()    # tamper-evident
```

Each entry hashes the previous entry, so any edit breaks the chain.

Continue to [Memory →](/guide/memory)
