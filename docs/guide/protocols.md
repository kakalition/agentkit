# MCP & A2A

agentkit speaks two agent protocols out of the box: **MCP** to consume external
tools, and **A2A** to expose and call other agents.

## MCP — Model Context Protocol

The MCP registry owns N MCP toolsets for the process lifetime. Each server's tools
are prefixed (`<server>_<tool>`) so names never collide.

```python
from agentkit.mcp import MCPRegistry, MCPServerSpec

registry = MCPRegistry([
    MCPServerSpec(name="chart", command="uvx", args=["mcp-server-chart"]),
    MCPServerSpec(name="fs", url="http://127.0.0.1:8931"),
])

await registry.__aenter__()                 # open once, for the process
toolset = await registry.toolset("chart")   # tools appear as chart_*
agent.toolset(toolset)
```

- **HTTP** servers are addressed by URL; **stdio** servers are launched directly.
- The registry is entered once and closed on shutdown — a long-running bot must not
  open a subprocess per message.
- `include_instructions` controls whether the server's instructions are surfaced.

The `MCPServerSpec` fields:

| Field | Purpose |
| --- | --- |
| `name` | the tool prefix |
| `command`, `args`, `env` | for stdio servers |
| `url` | for HTTP servers |
| `transport` | a prebuilt transport/client (used in tests) |

## Serving your agent over MCP

```python
from agentkit.mcp.server import serve_mcp
from fastmcp import FastMCP

server = FastMCP(name="nudge")

@server.tool
async def ask(prompt: str) -> str:
    return (await app.run(prompt)).output

serve_mcp(server, transport="streamable-http", host="127.0.0.1", port=8765)
```

## A2A — Agent-to-Agent

Expose an agent as an A2A server with a card, a task store, and an executor:

```python
from agentkit.a2a import (
    SQLAlchemyTaskStore, TaskAgentExecutor, build_a2a_app, build_card, serve_a2a,
)

card = build_card(
    name="nudge",
    description="A reminder agent.",
    url="http://127.0.0.1:9000",
    skills=[{"id": "reminders", "name": "Reminders", "tags": ["remind"]}],
)

app_ = build_a2a_app(
    card=card,
    executor=TaskAgentExecutor(app.answer),
    task_store=SQLAlchemyTaskStore(app.runtime),
    healthz=lambda: True,
)
serve_a2a(app_, host="127.0.0.1", port=9000)
```

`app.answer` is already a `(conversation_id, text) -> ChatResult` callable — exactly
the shape the A2A executor expects.

### Calling another agent

```python
from agentkit.a2a import A2AClient, load_peers

peers = load_peers("peers.json")
client = A2AClient(peers["researcher"])
reply = await client.send("Summarise the incident.")
```

## Skills in the agent card

A2A has its own notion of *skills*: they are **discovery metadata** on the agent
card (id, name, description, tags) that peers browse. They are distinct from
agentkit's [SKILL.md skills](/guide/skills), which are runtime instruction bundles.

## Topology

```
        ┌────────────┐   A2A (tasks)    ┌────────────┐
        │  nudge     │◀────────────────▶│ researcher │
        └─────┬──────┘                  └─────┬──────┘
    MCP (tools)                              MCP (tools)
        ▼                                    ▼
   chart server                        file server
```

Both protocols are transport concerns; your tools and agents are unchanged.

Continue to [Deployment →](/guide/deployment)
