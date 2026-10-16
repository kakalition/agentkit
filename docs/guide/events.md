# Events & Lifecycle

## Introduction

agentkit fires lifecycle events at the real seams of a turn, so you can observe and
react without patching internals. Wire listeners with `app.on(...)`.

```python
app.on("turn.end", lambda event: audit(event.conversation_id, event.output))
```

## The event object

A listener receives an `Event` whose payload keys are exposed as attributes:

```python
def on_turn_end(event):
    print(event.conversation_id, event.channel, event.output, event.usage)
```

You can also read the raw payload:

```python
event.name          # "turn.end"
event.payload       # {"conversation_id": ..., ...}
event.get("usage")  # safe access
```

A special `"*"` listener receives **every** event:

```python
app.on("*", lambda event: log.info("event: %s", event.name))
```

## Lifecycle events

| Event | When | Key payload |
| --- | --- | --- |
| `boot` | after the app boots | `app` |
| `turn.start` | a turn begins | `conversation_id`, `channel`, `text` |
| `channel.message` | an inbound message arrives | `conversation_id`, `channel`, `text` |
| `tool.start` | a tool call begins | `tool`, `args` |
| `tool.end` | a tool call returns | `tool`, `result` |
| `approval.asked` | tools were deferred for approval | `requests` |
| `guardrails.injection` | injection signals found in a tool result | `tool`, `signals` |
| `turn.end` | a turn completes | `conversation_id`, `output`, `usage`, `history_length` |

## Listening from a provider

Listeners are usually registered during `boot()`:

```python
class AuditProvider(Provider):
    def boot(self, app):
        def audit(event):
            async async with app.repositories() as repos:
                await repos.audit.append("turn.end", target=event.conversation_id)
        app.on("turn.end", audit)
```

Listener errors never break a turn or a tool — they are logged and swallowed, so
observability can fail safely.

## Async listeners

Sync listeners run inline. Async listeners are supported by the async dispatch
path (used by the framework); a sync `dispatch()` raises if it meets a coroutine,
and closes it to avoid warnings.

```python
async def notify(event):
    await pusher.send(event.conversation_id, event.output)

app.on("turn.end", notify)
```

## Dispatching your own events

```python
app.events.dispatch("notes.exported", count=12)

# from anywhere, against the current app:
await Events.dispatch_async("notes.exported", count=12)
```

## Ordering

Within an event, listeners run in registration order, with `"*"` listeners after
the named ones:

```
turn.end → [registered listeners…] → [wildcard listeners…]
```

::: tip Events observe; they do not drive
Use events for auditing, metrics, notifications, and cache invalidation. To
*change* a turn (rewrite input, block content, add timing), use
[middleware](/guide/middleware) or capabilities.
:::

Continue to [Middleware →](/guide/middleware)

## Live stream in the web UI

The **Events** page consumes `GET /api/events` (an SSE stream that emits a `hello`
frame then a `tick` snapshot every 5s) and renders the rolling snapshots. The SPA
parses SSE with `fetch` + `ReadableStream` (so the bearer token is sent), normalising
the CRLF frame separators that `sse-starlette` emits.
