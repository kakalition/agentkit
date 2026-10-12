# Configuration

agentkit is configured through environment variables (and an optional `.env`),
with sensible defaults so a working agent needs almost nothing. This page covers
the framework-level configuration: settings, layered sections, and directories.

## AgentSettings

`AgentSettings` is a pydantic-settings model. Every field can be set by an
environment variable of the same (upper-cased) name:

```bash
AGENT_NAME=nudge
OWNER_ID=me
OWNER_NAME=Ada
OPENAI_API_KEY=sk-...
MODEL_NAME=openai:gpt-4o-mini
```

```python
from agentkit import AgentSettings, get_settings

settings = get_settings()            # cached; reads env + .env
settings = AgentSettings(agent_name="nudge", owner_id="me")   # explicit
```

Precedence is **environment > `.env` > field defaults**, and the model is
case-insensitive with `extra="ignore"`.

The complete field list lives in the [Configuration reference](/reference/configuration).

## Layered config sections

For per-concern configuration, define a `Section` and register it on the app.
Sections layer three sources: **defaults < `config/<name>.py` < environment**.

```python
from agentkit import Section

class MemorySection(Section):
    env_prefix = "AGENTKIT_MEMORY_"
    enabled: bool = True
    recall_limit: int = 5
    backend: str = "hash"
```

Register and read:

```python
app.config("memory", MemorySection)
section = app.config("memory")   # MemorySection(...)
```

A `config/memory.py` file supplies lower-precedence values:

```python
# config/memory.py
config = {"recall_limit": 8}
```

And the environment — highest precedence — overrides both:

```bash
AGENTKIT_MEMORY_RECALL_LIMIT=12
```

Because `Section` is a pydantic model, values are coerced and validated.

## Directories

Everything an agent owns lives under its **agent home**, which defaults to
`<workspace_root>/<agent_name>`:

| Directory | Contents |
| --- | --- |
| `<home>/agent.db` | conversations, messages, usage, memory, knowledge, … |
| `<home>/SOUL.md` | the persona |
| `<home>/skills/` | discoverable skills |
| `<home>/prompts/` | versioned prompts |
| `<home>/logs/` | log files |
| `<home>/artifacts/` | generated files |

```bash
AGENTKIT_HOME=~/.agentkit          # the workspace root
AGENT_HOME=~/.agentkit/nudge       # an explicit home (overrides)
```

Agentkit creates these lazily; you rarely manage paths by hand.

## Filesystem-backed roots

Three features discover files from conventional directories. Each can be pointed
elsewhere with a setting:

| Feature | Default roots | Override |
| --- | --- | --- |
| Skills | `./skills`, `<home>/skills` | `SKILLS_DIR` |
| Prompts | `./prompts`, `<home>/prompts` | `PROMPTS_DIR` |
| Knowledge | — (you choose) | `KnowledgeBase.add_directory(path)` |

## Model and provider settings

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                 # for compatible providers
MODEL_NAME=openai:gpt-4o-mini
MODEL_TIMEOUT=60
```

`build_model(settings)` constructs a provider model with a timeout and SDK
retries; `model_settings(...)` and `usage_limits(...)` derive the per-run settings.
Any PydanticAI provider works.

## Observability

```bash
OBSERVABILITY=phoenix            # phoenix | otlp | console | off (default: phoenix)
OTLP_ENDPOINT=
LOG_JSON=false
LOG_LEVEL=INFO
```

See [Observability](/guide/observability).

## Web UI, A2A, MCP, Telegram

```bash
WEBUI_ENABLED=true
WEBUI_HOST=127.0.0.1
WEBUI_PORT=8787

A2A_PUBLIC_URL=http://127.0.0.1:9000
A2A_HOST=127.0.0.1
A2A_PORT=9000

MCP_HOST=127.0.0.1
MCP_PORT=8765

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
```

::: tip Keep secrets out of the repo
`.env` is for local development. In production, inject configuration through your
platform's secret store — agentkit reads plain environment variables, so anything
works.
:::

## Testing configuration

Bound your agent home to a temp directory in tests so nothing leaks:

```python
def test_something(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path))
    get_settings.cache_clear()
```
