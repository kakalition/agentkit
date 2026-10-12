# The Agent Builder

`Agent.make(...)` is a fluent builder that assembles a PydanticAI agent from small,
declarative pieces. It is the front door for constructing agents; internal modules
keep importing PydanticAI directly.

```python
from agentkit import Agent

agent = (
    Agent.make("nudge")             # name (and defaults)
    .persona()                      # SOUL.md
    .instructions("Be concise.")    # static instructions
    .memory()                       # durable memory tools
    .skills()                       # discover SKILL.md folders
    .knowledge(path="./docs")       # retrieval-augmented generation
    .tool(add_note)                 # a tool
    .output(str)                    # output type
    .build()                        # → pydantic_ai.Agent
)
```

::: tip `agentkit.Agent` is the builder
Application code uses `agentkit.Agent`. If you need the raw PydanticAI class, import
it explicitly:

```python
from pydantic_ai import Agent        # the PydanticAI agent
from agentkit import Agent           # the fluent builder
```
:::

## Identity

### `Agent.make(name, ...)`

```python
Agent.make(
    "nudge",
    deps_type=Deps,      # the RunContext payload type (default: agentkit.Deps)
    model=None,          # a model or model name
    description=None,    # a human description
)
```

### `.persona(text=None, *, loader=None)`

Attach the persona from `SOUL.md`. By default the persona is **read live on every
run**, so editing `SOUL.md` changes the agent's voice without a restart.

```python
Agent.make("nudge").persona()                       # <AGENT_HOME>/SOUL.md
Agent.make("nudge").persona("You are Nudge.")       # a literal persona
Agent.make("nudge").persona(loader=my_load_soul)    # a custom loader(settings)
```

### `.instructions(text)` and `.prompt(...)`

Append static instructions. `.prompt(...)` pulls from a
[prompt registry](/guide/prompts) or a file:

```python
agent = Agent.make("nudge").instructions("Be concise.")

# from a versioned prompts/ directory:
agent = Agent.make("nudge").prompt(prompts, "greeting", name="Ada")

# from a single markdown file:
agent = Agent.make("nudge").prompt("./prompts/system.md")
```

## Tools and delegation

### `.tool(fn, ...)` and `.tools(*fns)`

```python
agent.tool(add_note)
agent.tool(delete_note, requires_approval=True)
agent.tools(summarize, translate)
```

Full option reference is on the [Tools](/guide/tools) page.

### `.specialist(agent, *, name, description)`

Expose another agent as a delegation tool. Usage and model are forwarded, so token
accounting stays correct.

```python
agent.specialist(reminder_agent, name="handle_reminders", description="Set timed reminders.")
```

See [Orchestrator & Sub-Agents](/guide/orchestrator) for the full delegation
surface (`Orchestrator`, `make_delegate`, `delegate`, and sub-agent spawning).

### `.orchestrate(...)`

Register several specialists at once, by mapping or by tuples:

```python
agent.orchestrate({
    "handle_notes": (notes_agent, "Manage notes."),
    "handle_files": (files_agent, "Manage files."),
})

agent.orchestrate([(notes_agent, "handle_notes", "Manage notes.")])
```

## Capability bundles

These add a tool or instructions and are the fastest way to give an agent a skill.

### `.memory(enabled=True)`

Adds `remember`, `recall`, and `forget_memory` tools plus a "known facts" digest
injected into the instructions. See [Memory](/guide/memory).

### `.skills(registry=None, *, paths=None, enforce=False)`

Attaches a [skill registry](/guide/skills). With no argument, skills are discovered
from `skills_dir` (or `./skills` and `<AGENT_HOME>/skills`). Adds `list_skills`,
`load_skill`, and `read_skill_file`, plus a compact index in the instructions.

```python
from agentkit import SkillRegistry

agent.skills()                                             # discover
agent.skills(SkillRegistry.from_paths(["./skills"]))       # explicit
agent.skills(enforce=True)                                 # lock to allowed-tools
```

### `.knowledge(kb=None, *, path=None, index=True, limit=5)`

Attaches a [knowledge base](/guide/knowledge). Adds a `search_knowledge` tool and,
when `index=True`, a source listing in the instructions.

```python
from agentkit import KnowledgeBase

kb = KnowledgeBase(); kb.add_directory("./docs")
agent.knowledge(kb)
agent.knowledge(path="./docs")     # index a path directly
```

### `.workspace(root_or_sandbox, *, read_only=False)`

Gives the agent a confined workspace with `read_file`, `list_files`, `write_file`,
and `run_command`. Backed by PydanticAI's workspace layer.

```python
from agentkit import Sandbox

agent.workspace(Sandbox("./work"))
agent.workspace("./work", read_only=True)
```

### `.clarify(enabled=True)`

Adds the `ask_user` tool for [human clarification](/guide/hitl). Wire a handler
with `app.clarify(...)`.

### `.approvals(enabled=True)`

Enables human approval for tools marked `requires_approval=True` (deferred tool
calls). See [Human-in-the-Loop](/guide/hitl).

### `.policy(policy)`

Attaches a `ToolPolicy` that denies tools not in its allow-list at execution time.
See [Safety](/guide/safety).

## Models, output, and reliability

### `.output(type)` and `.output_validator(fn)`

```python
from pydantic import BaseModel

class Summary(BaseModel):
    title: str
    bullets: list[str]

def validate(ctx, summary: Summary) -> Summary:
    if not summary.bullets:
        raise ModelRetry("Provide at least one bullet.")
    return summary

agent = Agent.make("summarizer").output(Summary).output_validator(validate)
```

### `.model(m)` and `.retries(n)`

```python
agent.model("openai:gpt-4o-mini").retries(3)
```

### `.capability(c)` — anything from PydanticAI

Pass through any PydanticAI capability. Common ones have shortcuts:

```python
agent.web_search().web_fetch().thinking(effort="medium").caching().tool_search()
agent.image_generation().instrumentation()
```

See [Observability](/guide/observability) and [Streaming](/guide/streaming).

## Building

`.build(*, settings=None, model=None, events=None)` returns a
`pydantic_ai.Agent`. The result is cached, so repeated calls return the same
object. The app calls `build()` for you when it needs the primary agent:

```python
app.agent(Agent.make("nudge").instructions("…"))   # builder; built lazily
```
