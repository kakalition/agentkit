# Prompt Registry

## Introduction

Prompts are content, not code. The **prompt registry** keeps them in files, tracks
versions, and renders variables — so you can edit prompts without touching Python.

## Prompt files

Prompts live under `./prompts` and `<agent_home>/prompts` (override with
`PROMPTS_DIR`). Each is a markdown file with optional front matter:

```markdown
---
name: greeting
version: 3
description: Greets a new user
---

You are {persona}. Greet {user} warmly and offer to help.
```

The highest `version` wins when several files share a `name`.

## Using the registry

```python
from agentkit import PromptRegistry

prompts = PromptRegistry.from_settings().discover()
prompts.names()

text = prompts.render("greeting", persona="Nudge", user="Ada")
```

## Attaching to an agent

Use `.prompt(...)` on the builder — with a registry, a directory, a file, or a raw
template:

```python
# a registry + a named prompt (extra keywords are render variables)
agent = Agent.make("nudge").prompt(prompts, "greeting", persona="Nudge", user="Ada").output(str)

# a single markdown file
agent = Agent.make("nudge").prompt("./prompts/system.md")

# a directory (the prompt to load is named with name=)
agent = Agent.make("nudge").prompt("./prompts", name="greeting")
```

::: tip A variable named `name`
For a directory, `name=` selects the prompt. If your template also has a `{name}`
variable, render it from the registry instead: `prompts.render("greeting",
name="Ada")`.
:::

::: tip Prompts compose
`.prompt(...)` appends, so you can layer a persona, a task prompt, and house style
in order. The first block is the most important; later blocks refine.
:::

## Versioning strategy

Keep the old version in the file name and bump `version` in the front matter:

```
prompts/
  greeting.md          # version: 2
  greeting_v3.md       # version: 3  → selected
```

Or keep a single file and edit `version` — the registry always picks the highest.

## Prompt vs. persona

| Use | For |
| --- | --- |
| **Persona** (`SOUL.md`) | the agent's enduring identity and voice |
| **Prompts** (`prompts/*.md`) | specific, often-versioned task instructions |

Both feed the same `instructions` channel and are read at build time (the persona is
read live per run).

## Testing prompts

Because rendering is pure, prompts are easy to test:

```python
def test_greeting():
    prompts = PromptRegistry.from_paths(["./prompts"]).discover()
    assert "Ada" in prompts.render("greeting", persona="Nudge", user="Ada")
```

Continue to [MCP & A2A →](/guide/protocols)
