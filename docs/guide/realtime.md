# Realtime Voice

agentkit exposes a `RealtimeSession` contract — a duplex audio/text session — with
two drivers: an in-process `LoopbackRealtime` (the default) and a
`PydanticAIRealtime` wrapper (the `realtime` extra).

```python
from agentkit.realtime import LoopbackRealtime

session = LoopbackRealtime(model="loop")
assert isinstance(session, RealtimeSession)
await session.connect()
await session.send_text("hello")
async for event in session.stream_events():
    print(event)
```

## Drivers

| Driver | Requires | Notes |
| --- | --- | --- |
| `loopback` | — | deterministic duplex session; default |
| `pydantic_ai` | `agentkit[realtime]` | lazy-imports PydanticAI's realtime transport |

Select with `realtime_driver=pydantic_ai`. Missing the extra raises a
`ConfigurationError` naming `realtime`; construction stays import-safe.

The `RealtimeSession` contract:
`connect` · `send_audio` · `send_text` · `stream_events` · `interrupt` · `close`.
