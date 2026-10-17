# Surfaces & Channels

## Introduction

Beyond the web UI and CLI, an agent can be reached over chat channels, a terminal
UI, MCP, and natural-language scheduling. Channels and scheduling follow the
contract → driver pattern; the TUI and MCP server are thin surfaces over a booted
app.

## Channels

`channel_driver` selects the chat gateway:

| Driver | Transport |
| --- | --- |
| `log` (default) | writes outbound messages to the log |
| `telegram`, `slack`, `email`, `discord` | the bot gateways |
| `mattermost` | incoming webhook (`MATTERMOST_WEBHOOK_URL`) |
| `linear` | issue comments (`LINEAR_API_KEY`) |
| `webhook` | POST to a URL (`WEBHOOK_URL`) |

```bash
CHANNEL_DRIVER=mattermost
```

Each gateway implements `send(conversation_id, text)`; configuring one without its
required URL/token raises a `GatewayError` naming what is missing. Register your
own with `app.extend("channel", "mine", lambda app: MyGateway(app))`.

## DM pairing

With no allow-list a bot accepts everyone — unless **pairing** is enabled, in which
case only paired users are admitted:

```python
from agentkit import PairingRegistry

gateway.pairing = PairingRegistry()
code = gateway.pair("new-user")      # send this to the user
gateway.confirm_pairing("new-user", code)   # now they are allowed
```

Codes are single-use and TTL-bounded (`code_ttl_s`, default 15 min). The registry
is in-memory by default; set `pairing_driver=repository` to persist pairings to the
`gateway_pairings` table so they survive a restart (and are shared across
processes). Enable it for a gateway with `channel_pairing_enabled=True` — gateways
then adopt `app.pairing`.

## Durable mailbox (cross-process)

`mailbox_durable=True` spools inter-agent messages for at-least-once delivery; the
default spool is in-process (`MemorySpool`). Under an app with a repository runtime
the durable mailbox uses `RepositoryMailboxSpool`, which persists to the
`mailbox_messages` table, so a message spooled by one process is drained by
`receive` in another:

```python
from agentkit import Mailbox, RepositoryMailboxSpool

mailbox = Mailbox(registry, durable=True, spool=RepositoryMailboxSpool(app))
```

## Terminal UI

```bash
agentkit tui        # needs the 'tui' extra (pip install agentkit[tui])
```

The TUI boots `bootstrap:app`, runs each prompt through the same
`ChatRunner` path, and keeps one conversation (`tui:default`).

## Serving over MCP

```bash
agentkit mcp:serve --transport stdio
agentkit mcp:serve --transport http --host 127.0.0.1 --port 8765
```

or programmatically:

```python
from agentkit import serve_agent, build_agent_mcp_server

serve_agent(booted_app, transport="stdio")
server = build_agent_mcp_server(booted_app, name="my-agent")   # an `ask` tool
```

HTTP transports warn if not bound to loopback and attach the app authenticator.
See also [MCP & A2A](/guide/protocols).

## Natural-language scheduling

`parse_when` turns a phrase into a cron expression or a one-off time, and the
scheduler toolkit exposes an approval-gated `schedule_natural` tool:

```python
from agentkit import parse_when

parse_when("every day at 9am")     # cron 0 9 * * *
parse_when("every monday at 8:30") # cron 30 8 * * 1
parse_when("in 2 hours")           # once at now + 2h
```

```text
schedule_natural(when="every monday at 8am", task="send_digest")
```

The parser is conservative — anything it cannot parse returns `None`, so the agent
can ask for a clearer time instead of guessing.
