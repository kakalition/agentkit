# OpenAI-Compatible API

## Introduction

Agentkit can expose your agent behind the OpenAI Chat Completions shape so any
OpenAI client (or tool) can talk to it. It is **opt-in** (`OPENAI_API_ENABLED`),
uses the same [authentication](/guide/authentication) as the web UI, and records
usage per completion.

## Enable

```bash
AGENTKIT_OPENAI_API_ENABLED=true
```

## Endpoints

- `GET /v1/models` — lists the agent's configured model.
- `POST /v1/chat/completions` — maps the last user message to the agent's answer.
  Supports non-streaming JSON and streaming SSE (`"stream": true`), terminated by
  `data: [DONE]`.

```bash
curl -s localhost:8787/v1/chat/completions \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"model":"agentkit","messages":[{"role":"user","content":"hi"}]}'
```

The endpoint reuses the same `App.answer` path as the CLI/web UI, so tools,
memory, approvals, and learning all apply. Pass `conversation_id` in the body to
pin the conversation; otherwise it defaults to `openai:<owner>`.

## Client config

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8787/v1", api_key="<token>")
client.chat.completions.create(model="agentkit", messages=[{"role": "user", "content": "hi"}])
```

Continue to [Webhooks →](/guide/webhooks)
