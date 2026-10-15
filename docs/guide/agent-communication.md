# Agent Communication

## Introduction

Agents in agentkit can talk to each other: they discover peers, message them,
hand off a whole conversation, and delegate through an orchestrator. Everything
is built on one `AgentHandle` type that wraps a **local** agent or a **remote A2A
peer**, so calling code never branches on which it is.

## Registry and handles

```python
from agentkit import AgentHandle, AgentRegistry

registry = AgentRegistry()
registry.register(AgentHandle.local(researcher, capabilities=["search"]))
registry.register(AgentHandle.remote("peer", "https://peer.example/a2a", client=a2a))

handle = registry.resolve("search")      # by capability or name
reply = await handle.invoke(ctx, "find the docs")
```

## Mailbox

```python
from agentkit import Mailbox

mailbox = Mailbox(registry, events=app.events)
await mailbox.send("researcher", "look this up")          # fire-and-forget
reply = await mailbox.ask("researcher", "what is X?")     # request/response
answers = await mailbox.broadcast("standup in 5")         # everyone
```

`ask` never raises into the caller's loop: a failed peer returns an error
string and emits `agent.error`. `durable=True` persists messages through DBOS so
they survive a restart.

## Peer tools and handoff

Attach the peer tools to any agent so the model can use them:

```python
Agent.make("lead").agents(registry).mailbox(mailbox).full()
# tools: send_to, ask_agent, broadcast, list_agents, handoff_to
```

`handoff_to(agent, brief=None)` moves the **whole conversation** to another agent:
by default the target receives the full transcript (same conversation history);
pass `brief` to hand over a focused summary. Chains are capped by
`MAX_HANDOFFS` to prevent loops.

## Orchestrator / Supervisor

`Orchestrator` and `Supervisor` are one registry-driven implementation:

```python
from agentkit import Orchestrator, Supervisor   # both work

orch = Orchestrator(name="lead", instructions="route", events=app.events)
orch.add_specialist(writer, name="writer", tool_name="write", capabilities=["writing"])
orch.add_specialist(researcher, name="researcher", capabilities=["search"])
agent = orch.build()

handle = orch.route("search")     # capability-based routing
```

- Delegation forwards `deps`, `usage` and `model`, so token accounting stays
  correct.
- Ordered `fallbacks=[...]` are tried when a specialist fails.
- Lifecycle events are emitted on the app dispatcher: `agent.started`,
  `agent.finished`, `agent.message`, `agent.handoff`, `agent.error`.

`Supervisor({"writer": writer, "researcher": researcher})` builds the same kind
of agent from a mapping.
