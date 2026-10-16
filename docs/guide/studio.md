# Studio — Team Builder & Playground

The **Studio** is the operator UI for authoring multi-agent teams without editing
code: build a team, run it in a playground with a message-flow graph, and export
the Python that recreates it.

It complements the read-only **Teams** page (live, code-registered `TEAMS`) with a
persisted, editable *declarative* team definition.

## The declarative layer

Agents in agentkit are live objects (a PydanticAI agent, an `AgentHandle`, or a
callable), so they cannot be stored in the browser. `TeamDefinition` is the
serializable half — a team's shape:

```python
from agentkit import TeamDefinition, TeamMember

definition = TeamDefinition(
    name="squad",
    kind="supervisor",              # groupchat | supervisor | managed
    members=[
        TeamMember(name="researcher", description="finds sources"),
        TeamMember(name="writer", description="drafts the answer"),
    ],
    speaker="moderator",            # round_robin | moderator | all | selector | manual
    moderator="writer",
    max_turns=12,
)
```

Named members are resolved back to live agents at run time through a `resolve`
callable (by default, the app's `AgentRegistry` plus its primary agent):

```python
from agentkit import materialize_team, run_team_definition, render_team_code

runner = materialize_team(definition)                 # a GroupChatRunner / ManagedTeam
result = await run_team_definition(definition, "ship the feature")
print(result["transcript"], result["ledger"])

print(render_team_code(definition))                   # Python that rebuilds it
```

A member that resolves to no live agent becomes a placeholder that replies
`('<name>' is not a registered agent …)` — so you can prototype the shape first and
wire the agents in code later.

## In the web UI

Open **Studio** in the operator UI:

- **Builder** — name, kind, speaker, moderator, limits, instructions, and roster
  rows (add/remove members).
- **JSON** — export the current draft or paste/apply a definition.
- **Python** — generate the `register_team(...)` / `build_team(...)` snippet.
- **Playground** — run the team and inspect the transcript, the **message-flow
  graph** (speakers as nodes, turn transitions as directed edges), and — for a
  `managed` team — the ledger (plan, facts, tasks).
- **Activate** — register the definition into the in-process `TEAMS` registry so
  it is runnable from Chat as `team_<name>` (in-process only; use the exported
  Python to persist it across restarts).

Definitions are stored per owner in the `team_definitions` table.

## REST API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/studio/teams` | list saved definitions (+ kinds/speakers) |
| `POST` | `/api/studio/teams` | create or replace a definition |
| `DELETE` | `/api/studio/teams/{name}` | remove a definition |
| `GET` | `/api/studio/teams/{name}/code` | generated Python |
| `POST` | `/api/studio/teams/{name}/run` | playground run → transcript + ledger |
| `POST` | `/api/studio/teams/{name}/activate` | register into `TEAMS` in-process |

See also [Group Chat & Teams](/guide/group-chat) for the runtime pieces and
[Native Tools](/guide/native-tools) for running a team as a `team_<name>` tool.
