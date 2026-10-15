# Webhooks

## Introduction

Outbound webhooks let the agent push lifecycle events (turns, db writes, learning
reflections) to external systems. Deliveries are HMAC-signed, retried with bounded
backoff, and logged. Opt-in via `WEBHOOKS_ENABLED`.

## Register

```bash
agentkit webhook add https://example.com/hook --events turn.end,db.create --secret s3cr3t
agentkit webhook list
agentkit webhook delete 1
```

`--events` accepts comma-separated event names, or `*` (the default) for all.
Subscriptions live in the `webhooks` table, scoped to the owner.

## Delivery

When `FullStackProvider` boots with `WEBHOOKS_ENABLED=true`, a `WebhookDispatcher`
subscribes to the app's event bus. On each matching event it POSTs:

```json
{"event": "turn.end", "data": {"conversation_id": "cli:default"}}
```

with headers:

- `X-AgentKit-Event: turn.end`
- `X-AgentKit-Signature: sha256=<hex>` — HMAC-SHA256 of the raw body using the
  subscription's secret. Verify it before trusting the payload.

Every attempt is recorded in `webhook_deliveries` (`status`, `attempts`, `error`),
so failures are inspectable and never block the turn.

## Programmatic use

```python
from agentkit.webhooks import WebhookDispatcher, sign

dispatcher = WebhookDispatcher(runtime)
dispatcher.subscribe(app.events)
await dispatcher.emit("turn.end", {"conversation_id": "c1"})

# verify an inbound signature yourself
expected = sign(secret, raw_body)
```

Continue to [Deployment →](/guide/deployment)
