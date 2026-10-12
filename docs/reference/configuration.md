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
