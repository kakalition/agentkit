# Specs & Codegen

A **spec** is the serializable half of a subsystem object — an agent, team,
workflow, or eval. Specs round-trip through JSON, expose a JSON Schema (which
drives the Studio form renderer), and render to code. The live object is built by
a *materializer* registered alongside the model.

```python
from agentkit.specs import SPECS, SpecKind

SPECS.kinds()                 # ['agent', 'eval', 'team', 'workflow']
SPECS.schema_for("agent")     # JSON Schema
agent = SPECS.materialize("agent", {"name": "researcher", "instructions": "Find sources."})
report = await SPECS.run("eval", {"name": "smoke", "cases": [...]}, target=app)
```

## Kinds

| Kind | Model | Materializes to |
| --- | --- | --- |
| `agent` | `AgentDefinition` | a live PydanticAI agent |
| `team` | `TeamDefinition` | a `GroupChatRunner` / `ManagedTeam` |
| `workflow` | `WorkflowDefinition` | a `StateGraph` |
| `eval` | `EvalDefinition` | an `EvalSuite` |

`TeamDefinition` predates the spec layer and is registered as the `team` kind
without renaming, so `agentkit.studio.TeamDefinition` and `/api/studio/teams` keep
working. Because its `kind` field is the *runner* kind, the spec protocol uses
`spec_kind` for the spec-kind name.

## The spec store

Definitions persist in the `definitions` table via
`RepositorySpecStore` (`kind`, `name`, `version`, `spec`). Legacy
`team_definitions` rows are copied in with `kind="team"` at `init_db`
(idempotent; the old table is kept read-only for a release).

## Codegen

`render_spec(spec, target)` renders a spec to `python`, `yaml`, or `json`; the
`python` renderer dispatches on the spec kind. Extensions may register more
targets via `manifest.codegen`.

```bash
agentkit spec list
agentkit spec schema team
agentkit spec export team squad --target yaml -o squad.yaml
agentkit spec import squad.yaml
```

The `python` target emits runnable code that rebuilds the definition with real
agents (see `render_team_code`, `render_agent_code`, `render_workflow_code`).
