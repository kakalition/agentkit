# Memory

Memory lets an agent remember durable facts about the owner across conversations —
a name, preferences, timezones, recurring details — and recall them later.

## Enabling memory

Add `.memory()` to the builder:

```python
agent = (
    Agent.make("nudge")
    .instructions("Be concise.")
    .memory()
    .output(str)
    .build()
)
```

This does three things:

- adds **`remember`**, **`recall`**, and **`forget_memory`** tools;
- injects a **memory digest** into the instructions (the most recent facts);
- wires semantic recall when an embedder is configured, with a keyword fallback
  otherwise.

## Using memory

The model calls the tools itself. You can also reach memory directly through the
[facade](/guide/facades):

```python
from agentkit import Memory

await Memory.remember("My name is Ada", kind="person")
Memory.search("name")
Memory.all(limit=20)
Memory.forget(memory_id)
```

Facts are owner-scoped: one database, one owner, so nothing leaks between agents.

## How recall works

Each fact is embedded and stored. `recall` searches by cosine similarity and
appends keyword matches, so it degrades gracefully:

- with an embedder configured → semantic recall;
- with no embedder → keyword matching.

Embedders are pluggable via `agentkit.embeddings`:

```bash
MEMORY_EMBEDDING_BACKEND=sentence-transformers   # | fastembed | hash | none
MEMORY_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
MEMORY_EMBEDDING_DEVICE=cpu
```

`hash` is a fast, dependency-free backend for tests and offline development.

## The digest

`.memory()` injects a short digest of known facts so the model has them without
calling a tool every turn. You can render it yourself:

```python
from agentkit import memory_digest

with app.repositories() as repos:
    print(memory_digest(repos, limit=50))
```

## When to use memory vs. knowledge

| Use | For |
| --- | --- |
| **Memory** | small, mutable facts about the *owner* that the agent learns over time |
| **Knowledge** | a large, mostly-static *corpus* the agent should retrieve from |

If it is something you would put in a user profile, it is memory. If it is a
document, it is [knowledge](/guide/knowledge).

## Storing structured facts

Give facts a `kind` to keep them organised:

```python
await Memory.remember("Prefers async standups", kind="preference")
await Memory.remember("Ada", kind="person")
await Memory.remember("Europe/Lisbon", kind="date")
```

::: tip Let the agent decide
You rarely call `Memory.remember` yourself. Instruct the agent to save durable
facts ("remember the owner's timezone when they mention it") and it will use the
tools appropriately.
:::

Continue to [Skills →](/guide/skills)
