# Streaming

## Introduction

Streaming delivers the model's output token by token, so users see progress
immediately. agentkit's streaming records history, usage, and events exactly like a
normal turn.

## Streaming a turn

```python
async for event in app.stream("Tell me a story"):
    if event.kind == "text":
        print(event.text, end="", flush=True)
    elif event.kind == "final":
        print("\n\n" + event.result.output)
```

`app.stream(...)` yields `StreamEvent`s:

| `kind` | Payload |
| --- | --- |
| `"text"` | `text` — the next chunk |
| `"final"` | `result` — the completed `ChatResult` |

The return value mirrors `app.run`: the final `ChatResult` carries `output`,
`history_length`, `usage`, and `tool_calls`.

## Lower level: `ChatRunner.stream`

```python
async with app.repositories() as repos:
    runner = ChatRunner(app.deps(repos), agent=app.agent(), conversation_id="cli:1")
    async for event in runner.stream("hello"):
        ...
```

History is persisted when the stream completes, so the next turn continues the
conversation.

## Events during streaming

Lifecycle events fire as usual. Tool events (`tool.start` / `tool.end`) come from
the [lifecycle capability](/guide/middleware#middleware-vs-capabilities), which
runs during streaming too:

```python
app.on("tool.start", lambda event: print(f"[calling {event.tool}…]"))
```

## Streaming from a channel

Channels that support incremental updates can forward chunks to their transport.
The web UI does this over a websocket; a CLI channel can simply print them:

```python
async def run_turn(conversation_id: str, text: str) -> None:
    async for event in app.stream(text, conversation_id=conversation_id):
        if event.kind == "text":
            await transport.send_chunk(event.text)
        elif event.kind == "final":
            await transport.finish(event.result.output)
```

::: warning Streaming and middleware
Turn [middleware](/guide/middleware) wraps `run`, not `stream`. If a middleware
must apply to streamed turns, run it around the whole generator or move the logic
into a capability.
:::

Continue to [Human-in-the-Loop →](/guide/hitl)
