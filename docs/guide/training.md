# Trajectories & Migration

## Introduction

agentkit can export conversation data as **trajectories** for training or
evaluation, run the agent over a batch of prompts, and import an existing hub
(OpenClaw) into an agent home.

## Trajectory export

A trajectory is a normalized, JSON-serializable view of a conversation: the
system prompt (once) and an ordered list of steps (`user` / `assistant` /
`tool_call` / `tool_result`).

```python
from agentkit import export_trajectory

trajectory = export_trajectory(messages, compress=True)
# {"system_prompt": "...", "steps": [{"role": "user", ...}, ...], "count": 4}
```

`compress=True` (or `compress_messages`) elides the middle of large tool returns,
keeping head + tail — so exports stay small without losing the shape.

### CLI

```bash
agentkit trajectory                       # every conversation, as JSONL
agentkit trajectory -c telegram:42 -o one.jsonl
agentkit trajectory --compress            # elide large tool outputs
```

## Batch generation

```bash
agentkit generate prompts.jsonl --n 3 --out generations.jsonl
```

Each prompt (a JSONL `{"prompt": ...}` line or a plain line) is run `n` times as
an **ephemeral** conversation, so nothing is persisted. Results contain the
prompt, output, and usage.

## Migrating from OpenClaw

```bash
agentkit migrate openclaw ./my-claw-hub --target ~/.agentkit
agentkit migrate openclaw ./my-claw-hub --dry-run   # report only
```

The importer recognises `config.json`, `memories.jsonl` / `memory/*.md`,
`skills/**/SKILL.md`, `schedules.json`, and `channels.json`, normalizing them into
`<target>/import/` and `<target>/skills/`. It never modifies the source. `agentkit
migrate` with no arguments still migrates the database schema.

```python
from agentkit import migrate_openclaw

report = migrate_openclaw("./hub", target="~/.agentkit")
print(report.render())
```
