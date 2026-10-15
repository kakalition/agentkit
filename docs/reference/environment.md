# Environment

A copy-pasteable `.env` for a local agent. Everything here is optional except the
provider key.

```bash
# --- Identity / app ---------------------------------------------------------
AGENT_NAME=assistant
OWNER_ID=owner
OWNER_NAME=Owner
# Agents live under the workspace root at <root>/<AGENT_NAME> by default.
AGENTKIT_HOME=~/.agentkit
# Optional explicit override; blank uses AGENTKIT_HOME/AGENT_NAME.
AGENT_HOME=
LOG_LEVEL=INFO

# --- Model / provider -------------------------------------------------------
OPENAI_API_KEY=
OPENAI_BASE_URL=
MODEL_NAME=openai:gpt-4o-mini
MODEL_TIMEOUT=60

# --- Memory -----------------------------------------------------------------
MEMORY_ENABLED=true
# sentence-transformers | fastembed | hash | none
MEMORY_EMBEDDING_BACKEND=sentence-transformers
MEMORY_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
MEMORY_EMBEDDING_DEVICE=cpu

# --- Skills -----------------------------------------------------------------
SKILLS_ENABLED=true
SKILLS_DIR=

# --- Prompts ----------------------------------------------------------------
PROMPTS_DIR=

# --- Web UI -----------------------------------------------------------------
WEBUI_ENABLED=true
WEBUI_HOST=127.0.0.1
WEBUI_PORT=8787

# --- Observability ----------------------------------------------------------
# phoenix | console | otlp | off
OBSERVABILITY=phoenix
OTLP_ENDPOINT=
LOG_JSON=false

# --- Telegram ---------------------------------------------------------------
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=

# --- A2A --------------------------------------------------------------------
A2A_PUBLIC_URL=http://127.0.0.1:9000
A2A_CARD_NAME=Agent
A2A_HOST=127.0.0.1
A2A_PORT=9000
PEERS_FILE=

# --- MCP --------------------------------------------------------------------
MCP_HOST=127.0.0.1
MCP_PORT=8765

# --- Drivers (each subsystem resolves one; see /guide/drivers) --------------
CACHE_DRIVER=array              # array | null
PROMPTS_DRIVER=file             # file | memory
MEMORY_DRIVER=repository        # repository | in_memory
STORAGE_DRIVER=local            # local | memory
QUEUE_DRIVER=database           # database | sync
SCHEDULER_DRIVER=dbos           # dbos | memory
GUARDRAILS_DRIVER=regex         # regex | moderation
COMMS_DRIVER=mailbox            # mailbox | broadcast | pipeline | pubsub | ...
GRAPH_DRIVER=sequential         # sequential | parallel | checkpointed
CODE_EXECUTOR_DRIVER=local      # local | docker | jupyter | e2b (extras)

# --- Self-learning ----------------------------------------------------------
# Lessons are review-gated by default (stored ``proposed`` until approved).
LEARNING_REQUIRE_REVIEW=true
```

## Precedence

```
explicit arguments  >  environment variables  >  .env file  >  field defaults
```

For a layered [`Section`](/guide/configuration#layered-config-sections), the order
is `defaults < config/<name>.py < environment`.

## Boot target

The CLI boots `AGENTKIT_BOOTSTRAP` (default `bootstrap:app`):

```bash
AGENTKIT_BOOTSTRAP=nudge.bootstrap:app
```

## Notes

- **`AGENTKIT_HOME`** is the workspace root; **`AGENT_HOME`** overrides a single
  agent's home directly and takes precedence when set.
- **`memory_embedding_backend=hash`** is a fast, offline backend for tests.
- Paths are expanded (`~` supported).
- Lists like `TELEGRAM_ALLOWED_CHAT_IDS` accept space- or comma-separated values.
