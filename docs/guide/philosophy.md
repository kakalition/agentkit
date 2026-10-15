# Philosophy

## Introduction

agentkit is opinionated. This page explains the ideas behind the API, so the rest
of the documentation reads as a consequence of a few principles rather than a pile
of features.

## Developer experience is a feature

An agent framework is used every day, so the *feel* of the API matters as much as
its capability. agentkit borrows the ergonomics that have made Laravel productive
for a decade: a container, providers, facades, an expressive builder, and a
generator-driven CLI.

```python
agent = (
    Agent.make("nudge")
    .persona()
    .instructions("Be concise.")
    .tool(add_note)
    .memory()
    .output(str)
    .build()
)
```

Reads like a sentence. Tests as easily as it reads.

## Batteries included, but removable

Everything you need to ship is present: persistence, memory, retrieval,
scheduling, streaming, channels, and safety. But each piece is optional and
additive. You can start with a bare `App` and a single agent, then switch on
memory, skills, or the web UI when you need them — without rewrites.

The framework layer is a **superset** of the lower-level modules. Importing
`agentkit.foundation` never removes the ability to call `agentkit.session` or
`agentkit.scheduler` directly.

## Explicit lifecycle, no import-time magic

Importing a module should not *do* things. In agentkit, work happens in two phases
you can name and test:

1. `Provider.register()` — pure: bind concerns, no side effects.
2. `Provider.boot()` — side effects: register tasks, listeners, warm caches.

And the boot order is fixed and load-bearing:

```
all Provider.register()  →  all Provider.boot()  →  scheduler/services
```

This is why a scheduled task can be registered before the scheduler starts, and
why you can boot an app inside a test without touching the network.

## Progressive disclosure, at every level

The same idea appears twice:

- **Skills** keep the model's context cheap: it sees a short *name + description*
  index and pulls the full instructions only when a skill is relevant.
- **The docs** you are reading follow the same shape — start with the 60-second
  example, descend only as far as you need.

## Durable by default

Agents run in a single supervised process. Schedules survive restarts, workflows
retry, conversations persist, and the audit log is tamper-evident. "It works on my
laptop" and "it works in production" are the same binary.

## Safety is not a plugin

Approvals, human clarification, prompt-injection scanning, PII redaction,
moderation, budgets, and a hash-chained audit log are first-class surfaces, not
afterthoughts bolted on with a decorator. Risky tools are opt-in
(`requires_approval=True`), and policy is expressed once with a `ToolPolicy`.

## Build on the ecosystem

agentkit does not reinvent the model layer. It stands on
[PydanticAI](https://ai.pydantic.dev) for agents, MCP, and workspaces;
[DBOS](https://www.dbos.dev) for durable execution; `genai_prices` for cost;
`pydantic_evals` for evaluations; and standard libraries for everything else. When
a well-tested library exists, agentkit wires it in rather than cloning it.

::: tip The test of a good abstraction
If a feature makes the simple case harder, it does not belong in the builder. The
`Agent.make(...)` chain above will still be a one-liner when your agent has
memory, skills, retrieval, approvals, and observability.
:::

Continue to [The Application →](/guide/application)
