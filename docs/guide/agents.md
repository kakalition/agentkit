# The Agent Builder

## Introduction

An agent is defined as a **class** — the primary API. Subclass `AgentDefinition`,
declare what the agent is with class attributes, and the framework assembles the
PydanticAI agent from them. Any `app/Agents/*.py` subclass is discovered and
registered automatically.

```python
from agentkit import AgentDefinition

class Assistant(AgentDefinition):
    name = "assistant"
    description = "A concise, helpful assistant."
    posture = "hybrid"           # or "specialized" / "free"
    instructions = "You are a concise, helpful assistant."
    tools = [current_time]
    full = True                  # persona + memory + skills + HITL + safety
    output = str

agent = Assistant.build()        # → pydantic_ai.Agent
```

Every declaration maps to a call on the equivalent fluent builder
(`Agent.make(...)`):

| Declaration | Fluent equivalent |
| --- | --- |
| `name` / `description` / `deps_type` / `model` | `Agent.make(name, deps_type=…, model=…, description=…)` |
| `instructions` / `prompts` | `.instructions(…)` / `.prompt(…)` |
| `persona` | `.persona()` |
| `tools` / `toolsets` / `specialists` | `.tool(…)` / `.toolset(…)` / `.specialist(…)` |
| `memory` / `skills` / `knowledge` / `approvals` / `safety` / `workspace` / `learning` / `todos` / `code` / `guardrails` / `working_memory` | the matching capability bundle |
| `posture` | `.posture(…)` / `.specialized()` / `.free()` |
| `full = True` | `.full(…)` |
| `output` / `output_validators` / `retries` | `.output(…)` / `.output_validator(…)` / `.retries(…)` |

Anything not covered by a field goes in `configure(self, agent)` (or the legacy
`define`), which receives the builder and returns it:

```python
class Assistant(AgentDefinition):
    ...

    def configure(self, agent):
        agent.web_search().caching()
        return agent
```

`AgentDefinition.build(...)` returns the built PydanticAI agent directly:

```python
agent = Assistant.build()
```

## Identity

### `name`, `description`, `deps_type`, `model`

```python
class Nudge(AgentDefinition):
    name = "nudge"
    description = "Sends gentle reminders."
    deps_type = Deps            # the RunContext payload type (default: agentkit.Deps)
    model = None                # a model or "provider:model"
```

Fluent equivalent: `Agent.make("nudge", deps_type=Deps, model=None, description="…")`.

### `persona`

Attach the persona from `SOUL.md`. By default the persona is **read live on every
run**, so editing `SOUL.md` changes the agent's voice without a restart.

```python
class Nudge(AgentDefinition):
    persona = True              # reads <AGENT_HOME>/SOUL.md on every run
```

For a literal persona or a custom loader, use `configure`:

```python
class Nudge(AgentDefinition):
    def configure(self, agent):
        return agent.persona("You are Nudge.")
        # or: agent.persona(loader=my_load_soul)
```

Fluent equivalent: `Agent.make("nudge").persona()`.

### `instructions` and `prompts`

```python
class Nudge(AgentDefinition):
    instructions = "Be concise."
    prompts = ["./prompts/system.md"]      # a file or a raw template string
```

Fluent equivalent: `.instructions("Be concise.")` and
`.prompt("./prompts/system.md")`. For a named prompt from a registry (or a prompt
directory), use `configure` (`agent.prompt(registry, name="greeting")`); see
[Prompts](/guide/prompts).

## Tools and delegation

### `tools` and `toolsets`

```python
class Notes(AgentDefinition):
    tools = [add_note, delete_note, summarize, translate]
    toolsets = [my_toolset]
```

Approval flags live on the tool itself (`requires_approval=True`). Fluent
equivalent: `.tool(add_note)` (or `.tools(...)`) and `.toolset(my_toolset)`. See
[Tools](/guide/tools).

### `specialists`

Expose another agent as a delegation tool. Usage and model are forwarded, so token
accounting stays correct.

```python
class Assistant(AgentDefinition):
    specialists = {"handle_reminders": (reminder_agent, "Set timed reminders.")}
```

Fluent equivalent: `.specialist(reminder_agent, name="handle_reminders", description="Set timed reminders.")`.
See [Orchestrator & Sub-Agents](/guide/orchestrator) for the full delegation
surface (`Orchestrator`, `make_delegate`, `delegate`, and sub-agent spawning).

To register several specialists at once, use `configure`:

```python
def configure(self, agent):
    return agent.orchestrate({
        "handle_notes": (notes_agent, "Manage notes."),
        "handle_files": (files_agent, "Manage files."),
    })
```

### Teams

Attach a namespaced `team_<name>(prompt)` tool that runs a
[registered team](/guide/group-chat). Register the roster first, then attach it in
`configure`:

```python
from agentkit import register_team

register_team("squad", {"researcher": researcher, "writer": writer})

class Assistant(AgentDefinition):
    def configure(self, agent):
        return agent.team("squad")
```

## Capability bundles

These add a tool or instructions and are the fastest way to give an agent a skill.
Set the matching class field; each has a fluent equivalent.

### `memory = True`

Adds `remember`, `recall`, and `forget_memory` tools plus a "known facts" digest
injected into the instructions. Fluent equivalent: `.memory()`. See
[Memory](/guide/memory).

### `skills = True`

Attaches a [skill registry](/guide/skills): with no argument, skills are discovered
from `skills_dir` (or `./skills` and `<AGENT_HOME>/skills`). Adds `list_skills`,
`load_skill`, and `read_skill_file`, plus a compact index in the instructions.
Fluent equivalent: `.skills()`; for an explicit registry or `enforce=True`, use
`configure` (`agent.skills(SkillRegistry.from_paths(["./skills"]), enforce=True)`).

### `knowledge = <path|True>`

Attaches a [knowledge base](/guide/knowledge). `knowledge = "./docs"` indexes a
path; `knowledge = True` uses the app knowledge base. Fluent equivalent:
`.knowledge(path="./docs")` or `.knowledge(kb)`.

### `workspace = <dir>`

Gives the agent a confined workspace with `read_file`, `list_files`, `write_file`,
`edit_file`, `glob`, `grep`, and `run_command`, backed by PydanticAI's workspace
layer.

```python
class Assistant(AgentDefinition):
    workspace = "./work"          # or Sandbox("./work")
```

Fluent equivalent: `.workspace(Sandbox("./work"))`; pass `read_only=True` via
`configure`.

### `approvals = True`

Adds the `ask_user` tool for [human clarification](/guide/hitl) and enables human
approval for tools marked `requires_approval=True`. Wire a handler with
`app.clarify(...)`. Fluent equivalent: `.approvals()` and `.clarify()`.

### `safety = True` and `policy`

`safety = True` attaches `default_policy()` (a `ToolPolicy` that denies tools not
in its allow-list at execution time); pass a custom one with `policy = my_policy()`.
Fluent equivalent: `.policy(policy)`. See [Safety](/guide/safety).

### `posture`

Select a [posture](/guide/posture) — the default layer set for `full`. `hybrid` is
the default; an explicit field always wins.

```python
class Support(AgentDefinition):
    posture = "specialized"

class Scout(AgentDefinition):
    posture = "free"
```

Fluent equivalent: `.posture("free")`, `.specialized()`, `.free()`.

### `learning`, `todos`, `code`, `guardrails`, `working_memory`

```python
class Assistant(AgentDefinition):
    learning = True         # reflect -> learn -> apply (see Self-Learning)
    todos = True            # in-loop todo tools (see Tasks & Todos)
    code = True             # approval-gated run_code (see Code Execution)
    guardrails = True       # injection-scanning hooks (see Safety)
    working_memory = True   # thread-scoped working memory
```

Fluent equivalents: `.learning()`, `.todos()`, `.code_execution()`,
`.guardrails()`, `.working_memory()`.

### `agent_middleware`

```python
class Assistant(AgentDefinition):
    agent_middleware = [TimingMiddleware(), RedactionMiddleware()]
```

Fluent equivalent: `.agent_middleware(TimingMiddleware(), RedactionMiddleware())`.
See [Agent Middleware](/guide/agent-middleware).

## Native toolkits and self-learning

Every agentkit capability can be exposed as agent-callable tools. Each is opt-in,
gated by a settings flag, safe by default (deny-by-default allow-lists,
approval-gated writes), and idempotent. Their allow-lists have no class field, so
attach them in `configure`:

```python
class Assistant(AgentDefinition):
    def configure(self, agent):
        agent.database({"note": Note})    # CRUD over an allow-list of models
        agent.scheduler(["sync_notes"])   # manage schedules over allow-listed tasks
        agent.queue({"sync": SyncNotes})  # enqueue allow-listed jobs
        agent.notifications()             # notify / notify_me
        agent.history()                   # list / search / read conversations
        agent.usage()                     # usage + audit trail
        agent.knowledge_admin()           # index / replace / forget documents
        agent.skill_authoring()           # write SKILL.md files
        return agent
```

`learning = True` (or `.learning()`) adds the reflect -> learn -> apply loop. See
[Native Tools](/guide/native-tools), [Self-Learning](/guide/self-learning),
[Tasks & Todos](/guide/tasks), and [Code Execution](/guide/code-execution).

## `full = True`

`full = True` expands the class to the whole agent stack in one idempotent call.
Each layer is toggleable by its own field and skipped when its settings flag
disables it (`persona`, `memory`, `skills`, `knowledge`, `approvals`, `safety`,
`workspace`, `subagents`, `native`, `learning`, `todos`, `code`, `guardrails`,
`working_memory`). See the per-layer table on [The Full Stack](/guide/fullstack).

```python
class Assistant(AgentDefinition):
    name = "assistant"
    instructions = "You are a concise, helpful assistant."
    tools = [current_time]
    full = True
```

Fluent equivalent: `.full(models={"note": Note}, tasks=["sync_notes"], jobs={"sync": SyncNotes})`.

## Models, output, and reliability

### `output` and `output_validators`

```python
from pydantic import BaseModel

class Summary(BaseModel):
    title: str
    bullets: list[str]

def validate(ctx, summary: Summary) -> Summary:
    if not summary.bullets:
        raise ModelRetry("Provide at least one bullet.")
    return summary

class Summarizer(AgentDefinition):
    name = "summarizer"
    output = Summary
    output_validators = [validate]
```

Fluent equivalent: `.output(Summary).output_validator(validate)`.

### `model` and `retries`

```python
class Summarizer(AgentDefinition):
    model = "openai:gpt-4o-mini"
    retries = 3
```

Fluent equivalent: `.model("openai:gpt-4o-mini").retries(3)`.

### Anything from PydanticAI

Use `configure` to pass through any PydanticAI capability or shortcut:

```python
class Assistant(AgentDefinition):
    def configure(self, agent):
        agent.web_search().web_fetch().thinking(effort="medium").caching().tool_search()
        agent.image_generation().instrumentation()
        return agent
```

See [Observability](/guide/observability) and [Streaming](/guide/streaming).

## Building and discovery

Convention discovery builds and registers every `AgentDefinition` subclass under
`app/Agents/` — no manual registration is needed. `AgentDefinition.build(*,
settings=None, model=None, events=None)` returns the `pydantic_ai.Agent` directly
(the result is cached):

```python
agent = Assistant.build()
```

The app calls `build()` for you when it needs an agent. The fluent form
(`Agent.make(...)`) stays available for one-off, code-built agents — for example
`app.agent(Agent.make("nudge").instructions("…"))`.
