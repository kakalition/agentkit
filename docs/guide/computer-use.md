# Browser & Computer-Use

agentkit exposes a `Computer` contract — a controllable browser/desktop surface —
with two drivers: an in-process `LoopbackComputer` (the default) and a
headless-browser `PlaywrightComputer` (the `browser` extra).

```python
from agentkit.computer import LoopbackComputer, PlaywrightComputer

computer = LoopbackComputer()          # deterministic, dependency-free
snapshot = await computer.goto("https://example.com")
await computer.click("#submit")
await computer.type("#q", "agentkit")
state = await computer.evaluate("document.title")
```

## Drivers

| Driver | Requires | Notes |
| --- | --- | --- |
| `loopback` | — | in-memory, records actions; default |
| `playwright` | `agentkit[browser]` | lazy-imports Playwright on first use |

Select with `computer_driver=playwright`. Missing the extra raises a
`ConfigurationError` naming `browser`; construction stays import-safe.

## Tools

`toolkits.computer.attach_computer_tools(agent)` registers approval-gated
`browser_goto`, `browser_snapshot`, `browser_click`, `browser_type`,
`browser_screenshot`, and `browser_evaluate` tools. Every tool is approval-gated
by default and egress policy still applies.

```python
from agentkit import Agent
from agentkit.toolkits.computer import attach_computer_tools

agent = Agent.make("browser").build()
attach_computer_tools(agent)   # tools resolve the configured computer driver
```

The `Computer` contract:
`goto` · `snapshot` · `click` · `type` · `screenshot` · `evaluate` · `close`.
