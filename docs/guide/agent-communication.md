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

## Message topologies

### What this is, in plain English

Agents that work together need a way to pass messages. The shape of that passing
— *who is allowed to talk to whom, and how a message travels from sender to
receiver* — is called a **topology** (the word just means "the arrangement").

A topology is the postal system for your agents. Some systems are one-to-one
letter delivery with a named address; some are PA announcements to the whole
office; some are an assembly line where each station passes its work to the next.
They all carry the same payload — a message — but they move it differently, so you
choose the one that matches how your agents should cooperate.

Every topology satisfies one contract, `Topology`, with two methods:

```python
async def send(to, message, *, sender=None) -> bool: ...           # point-to-point
async def broadcast(message, *, to=None, sender=None) -> dict: ...  # fan-out
```

Handlers are registered per name with `register(name, handler)`. Because the
contract never changes, swapping topologies never changes your calling code.

::: tip Who can talk to whom
Changing the topology changes *routing*, not the agents themselves. The same two
agents can sit behind a `mailbox` (they address each other directly), a `hub`
(everything passes through one router), or a `pipeline` (a fixed order), and none
of their internal code changes.
:::

### A runnable example

```python
from agentkit import App, DriverKind

app = App()   # default topology: COMMS_DRIVER=mailbox

# Register a named handler; every topology routes by these names.
async def researcher(message):
    return f"researcher got: {message}"

app.comms.register("researcher", researcher)

# 1. Point-to-point: send() delivers to one name and returns whether it existed.
print(await app.comms.send("researcher", "look this up"))    # True

# 2. Switch topologies: the same send()/broadcast() contract, different routing.
fanout = app.manager(DriverKind.COMMS).driver("broadcast")
fanout.register("researcher", researcher)
print(await fanout.broadcast("standup in 5"))
# {'researcher': 'researcher got: standup in 5'}
```

### Built-in drivers

Kind `comms`, setting `COMMS_DRIVER`. Every driver implements the same
`send`/`broadcast` contract.

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `mailbox` | Default. Name-addressed delivery with inboxes; `send` is fire-and-forget, `ask` is request/response, `broadcast` fans out to the registry. | Agents mostly talk one-to-one and you want replies and durable options. |
| `broadcast` | Every message goes to every registered handler; the address is ignored. | You want a simple announcement to all agents. |
| `swarm` | Like `broadcast`, but returns every agent's reply. | You want all agents to answer and you collect the answers. |
| `pipeline` | Sequential stages: the output of one stage becomes the input of the next. | You have a fixed, ordered workflow (step 1, then step 2, then step 3). |
| `hub` | Every message is routed through one central hub handler. | You want a single dispatcher or router that knows where things go. |
| `mesh` | Peer-to-peer direct delivery between any two registered agents. | Your agents are equal peers with no central node. |
| `hierarchy` | Parent/child routing: messages flow to a designated parent handler. | You have a supervisor tree where children report to a parent. |
| `outbox` | Append-only: messages are recorded, never delivered. | You want to audit or queue outgoing messages. |
| `blackboard` | A shared board: messages are posted to channels all agents can read. | Agents share working memory through a common board. |
| `pubsub` | Topic publish/subscribe: `send(topic, message)` notifies the topic's subscribers. | Agents subscribe to topics rather than to each other. |
| `groupchat` | A group chat where a speaker strategy picks who answers each broadcast. | You want a moderated multi-agent discussion. |
| `handoff` | Single-step transfer: the message is handed to one handler and answered. | You just need to move one message to one specific agent. |

::: tip Group chat speaker strategies
`GroupChatTopology` chooses who answers each broadcast with a `GroupChatSpeaker`:
`round_robin` (default — rotate through the roster), `moderator` (always ask a
designated moderator), or `all` (ask everyone and collect the replies).
:::

### Selecting a driver

Precedence, as everywhere: explicit name, then setting, then default.

```bash
# .env
COMMS_DRIVER=pipeline
```

**Per app only.** Register a topology factory scoped to this app with `app.extend`:

```python
from agentkit import App, DriverKind
from agentkit.comms import HubTopology

app = App()
app.extend(DriverKind.COMMS, "myhub", lambda app: HubTopology(hub="dispatcher"))
```

**Reusable driver.** Ship a topology to the global registry for everyone:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.COMMS, "tree")
def _tree(app):
    return TreeTopology()   # an object with send() and broadcast()
```

Read more on [Contracts & Drivers](/guide/drivers).

### Where comms state lives

The *sender* of a message and *how deep* a handoff chain has gone are carried
first-class on `Deps.comms` as a `CommsContext`:

```python
from agentkit.deps import CommsContext

comms = CommsContext()   # comms.sender (str | None), comms.handoff_depth (int)
```

`Mailbox.ask` and `Mailbox.send` set `comms.sender` on the receiving agent's
`Deps`; a `handoff` increments `comms.handoff_depth` (capped by `max_handoffs`).
The older `extras["_mailbox_sender"]` and `extras["_handoff_depth"]` keys are still
honored for compatibility, so existing code keeps working.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `send(...)` returns `False` | the target name is not registered as a handler on that topology |
| `broadcast(...)` returns an empty dict | no handlers are registered, or the roster is empty |
| A `pipeline` stage sees the wrong text | a pipeline feeds each stage's *output* into the next stage's input |
| `ConfigurationError: unknown comms driver 'x'` | the name is misspelled or not registered / `extend`ed |
| Handoffs stop early | the chain hit `max_handoffs` (default 3) — raise it in settings if that is intended |
