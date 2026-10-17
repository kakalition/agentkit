# Posture

## Introduction

A **posture** is a thin defaults layer over the layers
[`.full()`](/guide/agents) already exposes, the settings flags, and the tool
policy. It never forks a code path: selecting a posture only changes *defaults*,
and an explicit builder argument or a settings flag always wins. One runtime,
three postures.

| Posture | For | Shape |
| --- | --- | --- |
| `specialized` | a closed, single-purpose specialist | persona + skills + approvals; egress/code/peers **denied** |
| `hybrid` | the general default | exactly today's `.full()` behavior |
| `free` | an autonomous generalist | `.full()` + workspace, code, egress, peers |

`hybrid` is the default, so existing applications are unaffected.

## Selecting a posture

```python
from agentkit import AgentDefinition

class Support(AgentDefinition):
    name = "support"
    posture = "specialized"    # closed specialist
    full = True

class Assistant(AgentDefinition):
    name = "assistant"
    posture = "hybrid"         # hybrid (default)
    full = True

class Scout(AgentDefinition):
    name = "scout"
    posture = "free"           # autonomous generalist
    full = True
```

Fluent equivalent:

```python
from agentkit import Agent

agent = Agent.make("support").specialized().full()   # closed specialist
agent = Agent.make("assistant").full()               # hybrid (default)
agent = Agent.make("scout").free().full()            # autonomous generalist
```

Or app-wide, which also seeds the posture into `deps.extras["posture"]`:

```python
from agentkit import Application

app = Application.configure(settings=Settings).withPosture("free").create()
```

Or from settings, so it can be environment-driven:

```bash
AGENT_POSTURE=specialized
```

## Precedence

The rule is one line — **explicit argument > builder method > posture > settings
flag** — and it is covered by tests. Settings flags remain a *hard gate*: a layer
whose flag is disabled stays disabled even when a posture would enable it.

```python
from agentkit import AgentDefinition

class X(AgentDefinition):
    name = "x"
    posture = "specialized"
    full = True
    memory = True          # explicit declaration re-enables memory
```

Fluent equivalent:

```python
Agent.make("x").specialized().full(memory=True)   # explicit arg re-enables memory
```

## What each posture changes

| Dimension | `specialized` | `hybrid` | `free` |
| --- | --- | --- | --- |
| Memory | off | on | on |
| Skills | discover (no authoring) | discover | discover + authoring |
| Approvals | required | `default_policy()` | only destructive/egress |
| Code / workspace | off | opt-in | on |
| Egress (web) | denied | opt-in | on |
| Prompt preamble | "focused specialist" | none | "autonomous generalist" |

The posture policy (`specialized_policy()` / `free_policy()`) is attached by
`.full(safety=True)`. A closed posture *denies* egress and code tools outright;
the open posture relaxes approvals but still gates destructive or
non-recoverable egress tool calls.

::: tip
`agentkit inspect` prints the active posture and the layers its profile derives,
so you can confirm what a build actually enabled.
:::

## Custom postures

```python
from agentkit import PostureProfile, register_posture

register_posture(
    "readonly",
    PostureProfile(
        name="specialized",
        preamble="Answer only from memory; never call a tool that writes.",
        layers={"memory": False, "native": False, "code": False},
    ),
)
```

A profile is `preamble`, `layers` (the `.full()` toggles), `settings_overrides`,
`policy_factory`, and optional `budget`.
