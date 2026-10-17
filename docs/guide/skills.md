# Skills

## Introduction

A **skill** is a folder of instructions the agent loads **on demand**. Inspired by
progressive disclosure, the model first sees only a cheap *name + description*
index, and pulls the full "how-to" only when a skill is relevant. This keeps the
context window small even with dozens of capabilities.

## Anatomy of a skill

```
skills/
  pdf-tools/
    SKILL.md              # front matter + instructions
    references/style.md   # bundled files
    scripts/extract.py
```

```markdown
---
name: pdf-tools
description: Extract text and tables from PDF files.
allowed-tools: [read_skill_file]
---

# PDF tools

Call `read_skill_file("pdf-tools", "references/style.md")` for house style, then
run the extractor in `scripts/extract.py`.
```

The front matter requires `name` and `description`. `allowed-tools` is optional
(used for [locking](/guide/skills#locking-tools-to-skills)).

## Discovering skills

Skills are discovered from `./skills` and `<agent_home>/skills`, or from an
explicit path:

```bash
SKILLS_ENABLED=true
SKILLS_DIR=              # override the roots
```

```python
from agentkit import SkillRegistry

registry = SkillRegistry.from_settings().discover()
registry.names()          # ["pdf-tools", ...]
registry.get("pdf-tools").description
```

## Attaching skills to an agent

```python
from agentkit import AgentDefinition

class Nudge(AgentDefinition):
    name = "nudge"
    instructions = "…"
    skills = True
    output = str

agent = Nudge.build()
```

Fluent equivalent:

```python
agent = Agent.make("nudge").instructions("…").skills().output(str).build()
```

`skills = True` (the fluent `.skills()`) adds:

- a compact **index** in the instructions (`- pdf-tools: Extract text…`);
- **`list_skills()`** — the index;
- **`load_skill(name)`** — the full instructions and bundled-file list;
- **`read_skill_file(name, path)`** — read a bundled file (path-traversal safe).

For an explicit registry or other `.skills(...)` sub-options there is no class
field, so use `configure` (the class field `skills = True` enables discovery):

```python
from agentkit import AgentDefinition, SkillRegistry

class Nudge(AgentDefinition):
    name = "nudge"
    skills = True                                          # enable discovery

    def configure(self, agent):
        return agent.skills(SkillRegistry.from_paths(["./skills"]))
```

## Locking tools to skills

Set `enforce=True` to restrict the agent's tools to the union of each skill's
`allowed-tools`. This is a "locked mode" — tools not declared by any skill are
denied at execution. There is no class field for `enforce`, so use `configure`:

```python
class Nudge(AgentDefinition):
    name = "nudge"
    skills = True

    def configure(self, agent):
        return agent.skills(registry, enforce=True)
```

The underlying policy is available directly:

```python
policy = registry.tool_policy(extra=["load_skill"])
```

## Bundled reference files

Large reference material lives as files next to `SKILL.md` and is read on demand.
`read_skill_file` refuses paths that escape the skill directory:

```python
registry.get("pdf-tools").files()          # ["references/style.md", "scripts/extract.py"]
registry.read_file("pdf-tools", "references/style.md")
registry.read_file("pdf-tools", "../secret")  # → error message, never the file
```

## Scaffolding

```bash
agentkit make:tool pdf_extract
```

## Authoring skills

The agent can write skills itself. `.skill_authoring()` adds two approval-gated
tools that render valid front matter and re-discover the registry. It has no class
field, so attach it in `configure`:

```python
class SkillAuthor(AgentDefinition):
    name = "skill-author"

    def configure(self, agent):
        return agent.skill_authoring()   # save_skill / update_skill
```

```python
# the model calls these (both require approval):
save_skill("Pdf Tables", "Extract tables from PDFs", "Call read_skill_file …")
update_skill("pdf-tables", "new instructions")
```

Under the hood, `write_skill_file` (from `agentkit.skills`) writes into the first
registry root and `slugify_skill` normalizes names.

## Distillation

The [self-learning](/guide/self-learning) loop can turn a **recurring lesson** into
a skill: once the same procedural lesson is seen `LEARNING_SKILL_THRESHOLD` times,
reflection reports a skill candidate and — with `LEARNING_AUTO_SKILLS=true` —
writes the `SKILL.md` for you.

## Inspecting from the CLI

```bash
agentkit skills list
agentkit skills show pdf-tools
```

::: tip Skills vs. plain instructions
A paragraph of instructions is fine for one capability. Skills earn their keep when
you have many, when the instructions are long, or when a capability ships its own
reference files and scripts.
:::

Continue to [Knowledge (RAG) →](/guide/knowledge)
