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
agent = Agent.make("nudge").instructions("…").skills().output(str).build()
```

`.skills()` adds:

- a compact **index** in the instructions (`- pdf-tools: Extract text…`);
- **`list_skills()`** — the index;
- **`load_skill(name)`** — the full instructions and bundled-file list;
- **`read_skill_file(name, path)`** — read a bundled file (path-traversal safe).

```python
agent.skills()                                        # discover from settings
agent.skills(SkillRegistry.from_paths(["./skills"]))  # explicit registry
```

## Locking tools to skills

Set `enforce=True` to restrict the agent's tools to the union of each skill's
`allowed-tools`. This is a "locked mode" — tools not declared by any skill are
denied at execution:

```python
agent.skills(registry, enforce=True)
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
