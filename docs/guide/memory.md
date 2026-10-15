# Memory

## Introduction

Memory lets an agent remember durable facts about the owner across conversations —
a name, preferences, timezones, recurring details — and recall them later.

Facts are typed (`fact`, `preference`, `person`, `date`, `episodic`,
`procedural`), ranked by a hybrid of semantic similarity, recency, and importance,
and tidied up by a durable `memory:consolidate` task. Memory tools and the facade
are **async**.

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
await Memory.search("name")
await Memory.all(limit=20)
await Memory.forget(memory_id)
```

Facts are owner-scoped: one database, one owner, so nothing leaks between agents.

## How recall works

Each fact is embedded and stored. `recall` ranks candidates by a weighted blend
of **semantic similarity**, **recency**, and **importance**, and appends keyword
matches so it degrades gracefully:

- with an embedder configured → semantic + hybrid ranking;
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

async with app.repositories() as repos:
    print(await memory_digest(repos, limit=50))
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

## The owner profile

Some facts belong in a profile rather than free-text memory. `OwnerProfile` stores a
name, timezone, locale, notes, and preferences, and the agent gets three tools for
it: `remember_person`, `update_profile`, and `get_profile`.

```python
from agentkit import Memory   # facade

async with app.repositories() as repos:
    await repos.profile.set(name="Ada", timezone="Europe/Lisbon")
    profile = await repos.profile.get()
```

## Lessons (procedural memory)

Memory also holds **procedural** lessons ("when X, do Y") learned by the agent. The
[self-learning](/guide/self-learning) loop stores them as `kind="procedural"` rows
and injects an importance-ranked digest into the instructions, so learned behaviour
changes future turns:

```python
await Memory.remember("When a deadline is mentioned, add a reminder", kind="procedural")
await Memory.all(kind="procedural")
```

Procedural lessons are deduped with `near_duplicates`/`merge` and can be distilled
into a `SKILL.md` once the same lesson recurs (see [Skills](/guide/skills)).

## Consolidation

Over time memory accumulates near-duplicates and stale entries. The durable
`memory:consolidate` task — registered and scheduled daily by `FullStackProvider` —
**dedupes** near-identical facts, **summarizes** long same-kind groups, and
**prunes** expired entries.

```bash
agentkit memory:consolidate --dry-run    # report only
agentkit memory:list --kind preference   # inspect
agentkit memory:forget 12                # delete one
agentkit memory:profile                  # show the profile
```

Consolidation is offline by default; pass a `summarizer` to fold a group with a
model instead of the heuristic.

Continue to [Skills →](/guide/skills)
