# Introduction

**agentkit** is a batteries-included framework for building, running, and shipping
durable AI agents in Python. It sits on top of [PydanticAI](https://ai.pydantic.dev)
and gives your agent the things every real service eventually needs — persistence,
memory, retrieval, scheduling, streaming, safety, and an operator UI — behind a
developer experience inspired by [Laravel](https://laravel.com).

If you have ever assembled an agent from a dozen disconnected libraries, agentkit
is the cohesive alternative: one framework, one process, one mental model.

## What is an agent, here?

An **agent** is a large-language-model program with instructions, tools, and state.
That is deliberately broad:

- a **personal assistant** that remembers your preferences and schedules reminders;
- a **support bot** that reads your knowledge base and escalates with approval;
- a **research workflow** that plans, calls tools, and delegates to specialists;
- a **coding helper** with a sandboxed workspace and code execution.

All of these are the same shape — *instructions + tools + state, run in a loop* —
so agentkit gives them the same primitives.

## What is in the box

agentkit ships the capabilities you would otherwise wire together yourself:

- **An application container.** `App`, service `Provider`s, class facades,
  configuration sections, an event bus, and a middleware pipeline.
- **A fluent agent builder.** `Agent.make(...)` composes instructions, tools,
  specialists, memory, skills, knowledge, and policies declaratively.
- **Persistence.** A libSQL/SQLite runtime with repositories for conversations,
  messages, usage, audit, memory, knowledge, feedback, and scheduled jobs.
- **Memory, skills, and retrieval.** Durable owner memory, discoverable `SKILL.md`
  folders, and an embedding-indexed knowledge base.
- **Durability.** Durable cron *and* one-off jobs plus DBOS-backed workflows.
- **Channels.** CLI, an operator web UI, Telegram, MCP, and A2A.
- **Production safety.** Approvals, clarification, injection/PII scanning,
  moderation, budgets, and a hash-chained audit log.
- **An Artisan-style CLI.** `serve`, `tinker`, `inspect`, `schedule:list`, and a
  family of `make:*` scaffolders.

## Why a framework?

You *can* build an agent by calling PydanticAI directly. agentkit exists for the
moment your prototype meets reality: when the conversation must persist, the
knowledge base must be searched, the risky tool must be approved, the job must
survive a restart, and someone has to *operate* the thing.

Rather than make you learn a new agent runtime, agentkit **builds on PydanticAI**
and stays close to it. Low-level modules (`agentkit.runtime`, `agentkit.session`,
`agentkit.scheduler`, …) remain available; the framework layer is an additive
front door.

::: tip New to agentkit?
Head to [Getting Started](/guide/getting-started) for a working agent in under a
minute, or read the [Philosophy](/guide/philosophy) if you want the *why* first.
:::

## Requirements

- Python **3.11+**
- An API key for a model provider (OpenAI by default; any PydanticAI provider works)
- No external services required — persistence, scheduling, and the web UI all run
  in-process by default

Continue to [Getting Started →](/guide/getting-started)
