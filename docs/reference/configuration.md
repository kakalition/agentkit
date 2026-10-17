# Configuration Reference

`AgentSettings` is a pydantic-settings model. Every field maps to an environment
variable of the same upper-cased name, and `get_settings()` returns a cached
instance built from the environment and `.env`.

## Identity

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `agent_name` | `AGENT_NAME` | `assistant` | The agent's name (also its home directory) |
| `owner_id` | `OWNER_ID` | `owner` | Owner scope for all stored data |
| `owner_name` | `OWNER_NAME` | `Owner` | A friendly owner name |

## Model

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `openai_api_key` | `OPENAI_API_KEY` | `None` | Provider API key |
| `openai_base_url` | `OPENAI_BASE_URL` | `None` | Compatible-provider base URL |
| `model_name` | `MODEL_NAME` | `openai:gpt-4o-mini` | Default model reference |
| `model_timeout` | `MODEL_TIMEOUT` | `60.0` | Transport timeout (seconds) |
| `model_retries` | `MODEL_RETRIES` | `2` | SDK retries |
| `usage_request_limit` | `USAGE_REQUEST_LIMIT` | `None` | Per-run request ceiling |
| `usage_total_tokens_limit` | `USAGE_TOTAL_TOKENS_LIMIT` | `None` | Per-run token ceiling |

## Persona, memory, skills, prompts

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `soul_file` | `SOUL_FILE` | `None` | Path to `SOUL.md` (default `<home>/SOUL.md`) |
| `memory_enabled` | `MEMORY_ENABLED` | `True` | Enable the memory tools |
| `memory_embedding_backend` | `MEMORY_EMBEDDING_BACKEND` | `sentence-transformers` | `sentence-transformers` / `fastembed` / `hash` / `none` |
| `memory_embedding_model` | `MEMORY_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `memory_embedding_device` | `MEMORY_EMBEDDING_DEVICE` | `cpu` | `cpu` / `cuda` / `mps` |
| `memory_embedding_query_prompt` | `MEMORY_EMBEDDING_QUERY_PROMPT` | `""` | Instruction-aware prefix for queries |
| `memory_embedding_document_prompt` | `MEMORY_EMBEDDING_DOCUMENT_PROMPT` | `""` | Instruction-aware prefix for documents |
| `skills_enabled` | `SKILLS_ENABLED` | `True` | Enable skill discovery |
| `skills_dir` | `SKILLS_DIR` | `None` | Override skill roots |
| `prompts_dir` | `PROMPTS_DIR` | `None` | Override prompt roots |

## Storage & workspace

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `workspace_root` | `AGENTKIT_HOME` | `~/.agentkit` | Root for all agent homes |
| `agent_home` | `AGENT_HOME` | `<workspace_root>/<agent_name>` | This agent's home |
| `database_url` | `DATABASE_URL` | `sqlite+libsql:///<home>/agent.db` | Database URL |
| `libsql_auth_token` | `LIBSQL_AUTH_TOKEN` | `None` | Token for remote libSQL |

Derived paths: `settings.home`, `settings.db_path`, `settings.artifacts_dir`,
`settings.logs_dir`. Call `settings.ensure_dirs()` to create them.

## Drivers

Every pluggable subsystem resolves one driver per settings field. Each field is
typed with its driver enum (from `agentkit.support.kinds`), so an invalid value
is rejected at settings load. See [Contracts & Drivers](/guide/drivers).

| Field | Env | Default | Values |
| --- | --- | --- | --- |
| `cache_driver` | `CACHE_DRIVER` | `array` | `array`, `null` |
| `prompts_driver` | `PROMPTS_DRIVER` | `file` | `file`, `memory` |
| `memory_driver` | `MEMORY_DRIVER` | `repository` | `repository`, `in_memory` |
| `memory_recall_driver` | `MEMORY_RECALL_DRIVER` | `hybrid` | `hybrid`, `keyword`, `recency` |
| `chunker_driver` | `CHUNKER_DRIVER` | `semantic` | `semantic`, `fixed` |
| `retriever_driver` | `RETRIEVER_DRIVER` | `repository` | `repository`, `memory` |
| `reranker_driver` | `RERANKER_DRIVER` | `identity` | `identity`, `lexical` |
| `storage_driver` | `STORAGE_DRIVER` | `local` | `local`, `memory` |
| `queue_driver` | `QUEUE_DRIVER` | `database` | `database`, `sync` |
| `scheduler_driver` | `SCHEDULER_DRIVER` | `dbos` | `dbos`, `memory` |
| `durability_driver` | `DURABILITY_DRIVER` | `dbos` | `dbos`, `temporal` (extra) |
| `database_driver` | `DATABASE_DRIVER` | `sqlite` | `sqlite`, `postgres` |
| `observability` | `OBSERVABILITY` | `phoenix` | `phoenix`, `console`, `otlp`, `off` |
| `pricing_driver` | `PRICING_DRIVER` | `genai` | `genai`, `static` |
| `rate_limit_driver` | `RATE_LIMIT_DRIVER` | `database` | `database`, `memory` |
| `auth_driver` | `AUTH_DRIVER` | `default` | `default`, `anonymous` |
| `vault_driver` | `VAULT_DRIVER` | `fernet` | `fernet`, `env` |
| `guardrails_driver` | `GUARDRAILS_DRIVER` | `regex` | `regex`, `moderation` |
| `ingest_driver` | `INGEST_DRIVER` | `default` | `default`, `text` |
| `audio_driver` | `AUDIO_DRIVER` | `openai` | `openai` |
| `learning_extractor_driver` | `LEARNING_EXTRACTOR_DRIVER` | `model` | `model`, `heuristic` |
| `learning_strategy_driver` | `LEARNING_STRATEGY_DRIVER` | `reflect_apply` | `reflect_apply`, `none` |
| `learning_sink_driver` | `LEARNING_SINK_DRIVER` | `memory` | `memory` |
| `comms_driver` | `COMMS_DRIVER` | `mailbox` | `mailbox`, `broadcast`, `swarm`, `pipeline`, `hub`, `mesh`, `hierarchy`, `outbox`, `blackboard`, `pubsub`, `groupchat`, `handoff` |
| `context_driver` | `CONTEXT_DRIVER` | `isolated` | `isolated`, `shared`, `summarized` |
| `tasks_driver` | `TASKS_DRIVER` | `memory` | `memory` |
| `planning_driver` | `PLANNING_DRIVER` | `single` | `single`, `batched` |
| `agent_middleware_driver` | `AGENT_MIDDLEWARE_DRIVER` | `noop` | `noop`, `logging` |
| `graph_driver` | `GRAPH_DRIVER` | `sequential` | `sequential`, `parallel`, `checkpointed` |
| `code_executor_driver` | `CODE_EXECUTOR_DRIVER` | `local` | `local`, `docker`, `jupyter`, `e2b` (extras) |
| `evals_reporter_driver` | `EVALS_REPORTER_DRIVER` | `text` | `text`, `json`, `pydantic` |
| `channel_driver` | `CHANNEL_DRIVER` | `log` | `log`, `telegram`, `slack`, `email`, `discord` |
| `notification_channel_driver` | `NOTIFICATION_CHANNEL_DRIVER` | `log` | `log`, `conversation`, `telegram` |
| `checkpoint_driver` | `CHECKPOINT_DRIVER` | `repository` | `repository`, `file`, `memory` |
| `computer_driver` | `COMPUTER_DRIVER` | `loopback` | `loopback`, `playwright` (extra) |
| `realtime_driver` | `REALTIME_DRIVER` | `loopback` | `loopback`, `pydantic_ai` (extra) |
| `catalog_driver` | `CATALOG_DRIVER` | `local` | `local`, `skills`, `http`, `git` |
| `dataset_driver` | `DATASET_DRIVER` | `repository` | `repository`, `memory` |
| `vector_store_driver` | `VECTOR_STORE_DRIVER` | `repository` | `repository`, `sqlite_vec` (extra), `pgvector` |
| `working_memory_driver` | `WORKING_MEMORY_DRIVER` | `memory` | `memory`, `repository` |
| `pairing_driver` | `PAIRING_DRIVER` | `memory` | `memory`, `repository` |
| `eval_grader_driver` | `EVAL_GRADER_DRIVER` | `exact` | `exact`, `contains`, `schema`, `trace`, `llm_judge` |

`memory_embedding_backend` doubles as the `embeddings` driver name
(`sentence-transformers` | `fastembed` | `hash` | `none`).

## Durability

`durability_driver=dbos` is the default (DBOS Transact over a local SQLite system
database). `durability_driver=temporal` (needs the `temporal` extra) routes durable
execution through Temporal; workflows are submitted by fully-qualified name, so the
worker must register them.

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `temporal_address` | `TEMPORAL_ADDRESS` | `localhost:7233` | Temporal frontend address |
| `temporal_namespace` | `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `temporal_task_queue` | `TEMPORAL_TASK_QUEUE` | `agentkit` | default task queue for enqueues/schedules |

## Mailbox & pairing persistence

`mailbox_durable` spools inter-agent messages (`mailbox_messages` table via
`RepositoryMailboxSpool`); `pairing_driver=repository` persists gateway pairings
(`gateway_pairings` table via `RepositoryPairingRegistry`). Both tables are created
additively by `init_db`.

## Studio, traces & checkpoints

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `run_trace_enabled` | `RUN_TRACE_ENABLED` | `True` | persist a uniform `RunEvent` trace per run (`run_events`) |
| `run_events_retention` | `RUN_EVENTS_RETENTION` | `2000` | max events kept per run |
| `checkpoints_enabled` | `CHECKPOINTS_ENABLED` | `False` | record run checkpoints (time travel) |
| `checkpoint_retention` | `CHECKPOINT_RETENTION` | `50` | max checkpoints kept per run |
| `computer_headless` | `COMPUTER_HEADLESS` | `True` | run the Playwright browser headless |
| `computer_timeout_ms` | `COMPUTER_TIMEOUT_MS` | `30000` | Playwright default timeout |
| `realtime_model` | `REALTIME_MODEL` | `None` | model for the realtime session |
| `catalog_dir` | `CATALOG_DIR` | `None` | directory for the `local` catalog (default `catalog`) |
| `catalog_url` | `CATALOG_URL` | `None` | JSON index URL for the `http`/`git` catalog |
| `catalog_repo` | `CATALOG_REPO` | `None` | git repo for the `git` catalog |
| `catalog_ref` | `CATALOG_REF` | `main` | git ref for the `git` catalog |
| `catalog_path` | `CATALOG_PATH` | `catalog.json` | index path inside the git repo |

## Capability depth

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `working_memory_enabled` | `WORKING_MEMORY_ENABLED` | `False` | add thread-scoped working-memory tools to every agent |
| `guardrails_enabled` | `GUARDRAILS_ENABLED` | `False` | scan tool results for prompt injection |
| `guardrails_wrap_untrusted` | `GUARDRAILS_WRAP_UNTRUSTED` | `False` | wrap untrusted tool results as data (attaches the hooks) |
| `online_scoring_enabled` | `ONLINE_SCORING_ENABLED` | `False` | grade live run traces with a registered grader |
| `online_scoring_grader` | `ONLINE_SCORING_GRADER` | `trace` | grader name for online scoring |
| `model_fallbacks` | `MODEL_FALLBACKS` | `[]` | ordered `provider:model` fallbacks for the primary model |

## Web UI

| Field | Env | Default |
| --- | --- | --- |
| `webui_enabled` | `WEBUI_ENABLED` | `True` |
| `webui_host` | `WEBUI_HOST` | `127.0.0.1` |
| `webui_port` | `WEBUI_PORT` | `8787` |

## Observability

| Field | Env | Default | Meaning |
| --- | --- | --- | --- |
| `observability` | `OBSERVABILITY` | `phoenix` | `phoenix` / `otlp` / `console` / `off` |
| `otlp_endpoint` | `OTLP_ENDPOINT` | `None` | Custom OTLP collector |
| `log_level` | `LOG_LEVEL` | `INFO` | Log level |
| `log_json` | `LOG_JSON` | `False` | JSON logs |

## Telegram

| Field | Env | Default |
| --- | --- | --- |
| `telegram_bot_token` | `TELEGRAM_BOT_TOKEN` | `None` |
| `telegram_allowed_chat_ids` | `TELEGRAM_ALLOWED_CHAT_IDS` | `[]` |
| `telegram_seen_reaction` | `TELEGRAM_SEEN_REACTION` | `True` |
| `telegram_live_status` | `TELEGRAM_LIVE_STATUS` | `True` |
| `telegram_typing_action` | `TELEGRAM_TYPING_ACTION` | `True` |
| `telegram_status_interval_s` | `TELEGRAM_STATUS_INTERVAL_S` | `2.5` |

## A2A & MCP

| Field | Env | Default |
| --- | --- | --- |
| `a2a_public_url` | `A2A_PUBLIC_URL` | `http://127.0.0.1:9000` |
| `a2a_card_name` | `A2A_CARD_NAME` | `Agent` |
| `a2a_host` | `A2A_HOST` | `127.0.0.1` |
| `a2a_port` | `A2A_PORT` | `9000` |
| `peers_file` | `PEERS_FILE` | `None` |
| `mcp_host` | `MCP_HOST` | `127.0.0.1` |
| `mcp_port` | `MCP_PORT` | `8765` |

::: tip
Because these are pydantic fields, their env names are case-insensitive and
values are coerced. `.env` is read from the working directory; environment
variables always win.
:::
