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

## Drivers

### What this is, in plain English

Memory is your agent's **filing cabinet of durable facts about the owner** — a
name, a timezone, a preference such as "prefers async standups". Two separate
decisions make it work, and agentkit lets you change each one independently:

1. **Where the notes are kept** — the *memory store*. The default writes each fact
   as a row in the same local database as your conversations; an alternative keeps
   them only in the running program.
2. **How we decide which notes to hand back** — the *recall strategy*. When the
   agent asks "what do I know about the user's name?", something has to rank the
   stored facts. The default blends three signals; alternatives use only one.

An **embedding** is just a list of numbers that captures the *meaning* of a
sentence, so two phrases about the same idea sit close together even when they
share no words. The default recall uses those numbers; the `keyword` strategy does
not need them at all.

::: tip The librarian analogy
Think of a library. The **store** is the building where the books live. The
**recall strategy** is the librarian who decides which books to bring back. The
`hybrid` librarian weighs how well a book matches your question, how recently it
was borrowed, and how important it is. The `keyword` librarian only fetches books
whose titles literally contain your words. The `recency` librarian hands you
whatever was touched most recently.
:::

### A runnable example

```python
import asyncio
from agentkit import App, DriverKind

async def main():
    # Build an app; both settings are read here (defaults are used when unset).
    app = App()                       # MEMORY_DRIVER=repository, MEMORY_RECALL_DRIVER=hybrid
    store = app.memory                # the configured memory store driver
    print(app.manager(DriverKind.MEMORY).available())         # ['in_memory', 'repository']
    print(app.manager(DriverKind.MEMORY_RECALL).available())  # ['hybrid', 'keyword', 'recency']

    # Save a durable fact through the MemoryStore contract.
    memory_id = await store.remember("My name is Ada", kind="person")

    # Recall by meaning; the hybrid strategy ranks the results.
    hits = await store.search("what should I call you", limit=3)
    print(memory_id, [hit.content for hit in hits])

    # Switch driver for one call by naming a different one explicitly.
    ephemeral = app.manager(DriverKind.MEMORY).driver("in_memory")
    print(await ephemeral.all())      # a fresh, empty in-memory store

asyncio.run(main())
```

Switch the whole application by changing the environment variables:

```bash
MEMORY_DRIVER=in_memory          # facts live only for this process
MEMORY_RECALL_DRIVER=keyword     # rank by literal word overlap
```

### Built-in drivers

**Memory stores — setting `MEMORY_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `repository` | Persists facts as owner-scoped rows in the agent database | Default. You want memory to survive restarts |
| `in_memory` | Holds facts in a Python dictionary for the life of the process | Tests, demos, throwaway agents |

**Recall strategies — setting `MEMORY_RECALL_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `hybrid` | Weighted blend of similarity, recency, and importance | Default; best general behaviour |
| `keyword` | Ranks by plain substring match, no embeddings needed | No embedder available; exact, predictable lookup |
| `recency` | Ranks purely by how recently a fact was used or updated | You want the most recent facts first |

The store must provide the `MemoryStore` contract — `remember`, `search`, `all`,
`forget`. The strategy must provide `RecallStrategy.score(query, similarity,
memory, now)`.

### How to select it

Selection follows the same precedence everywhere in agentkit:

1. **An explicit name in code** — `app.manager(DriverKind.MEMORY).driver("in_memory")`.
2. **The setting** — `MEMORY_DRIVER` / `MEMORY_RECALL_DRIVER`, read from the
   environment or a `.env` file.
3. **The default** — `repository` and `hybrid`, listed first in the tables above.

**Accessors:** `app.memory` returns the configured store, and
`app.manager(DriverKind.MEMORY)` gives the manager (`.driver()`, `.available()`,
`.configured_driver()`, `.forget()`). Recall is resolved through
`DriverKind.MEMORY_RECALL`.

Override a driver for one app only (this never leaks into other apps or the global
registry):

```python
from agentkit import DriverKind

app.extend(DriverKind.MEMORY, "scratch", lambda app: MyMemoryStore(app))
# then select it: MEMORY_DRIVER=scratch
```

Ship a reusable driver to every app that imports your package with
`@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.MEMORY, "scratch")
def _scratch(app):
    return MyMemoryStore(app)
```

A driver needs no base class — only the contract's methods. See
[Contracts & Drivers](/guide/drivers) for the full catalog, precedence, and the
conformance tests every driver must pass.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Recall returns nothing relevant | No embedder configured, so ranking fell back to keyword matching and missed paraphrases |
| Facts vanish after a restart | You selected the `in_memory` store |
| `ValidationError` when settings load | A typo in `MEMORY_DRIVER` or `MEMORY_RECALL_DRIVER` |
| A driver change had no effect | The manager caches one instance per app; call `app.manager(...).forget()` or restart |
| `ConfigurationError: unknown memory driver` | The selected driver is not registered — check spelling, or `app.extend(...)` it first |
