# Multimodal & Voice

## Introduction

Agents can accept more than text: images, audio, and documents. agentkit provides
helpers to build content parts and to capture generated media.

## Sending multimodal input

Build content parts and pass them to `app.run`:

```python
from agentkit import App, content, document, image, text

result = await app.run(
    content(
        text("What is in this photo, and does it match the invoice?"),
        image("receipt.jpg"),
        document("invoice.pdf"),
    ),
    conversation_id="cli:1",
)
```

`content(...)` composes a list of parts; a plain string is also a valid message, so
`app.run("hello")` and `app.run(content(text("hello")))` are equivalent.

### The part helpers

| Helper | Accepts | Produces |
| --- | --- | --- |
| `text(str)` | a string | text |
| `image(source)` | a path, bytes, or URL | an image part (`BinaryContent` / `ImageUrl`) |
| `audio(source)` | a path or bytes | an audio part |
| `document(source)` | a path or bytes | a document part (e.g. PDF) |

Media types are inferred from the file extension; override when needed:

```python
image("scan.bin", media_type="image/tiff")
document(blob, media_type="application/pdf")
```

## Generated media as artifacts

When a model returns generated media (for instance via `.image_generation()`), it
is captured automatically:

```python
agent = Agent.make("designer").instructions("…").image_generation().build()

result = await app.run("draw a mascot")
for artifact in result.artifacts:
    print(artifact["kind"], artifact["media_type"], artifact["bytes"])
```

You can also scan messages yourself:

```python
from agentkit.multimodal import collect_artifacts

collect_artifacts(result_messages)
```

Tools can declare their own artifacts via `ctx.deps.remember_artifact(kind, path)`.

## Speech: transcription and synthesis

`agentkit.audio` wraps the OpenAI audio API. Pass a path or bytes; pass a custom
`client` to test offline.

```python
from agentkit import synthesize, transcribe

transcript = transcribe("standup.m4a", language="en")
open("summary.mp3", "wb").write(synthesize("Here is your summary."))
```

```python
# inject a client (e.g. for a different provider or in tests)
transcribe(blob, client=my_client, model="whisper-1")
synthesize("hi", client=my_client, voice="alloy", response_format="mp3")
```

::: warning Realtime voice is not included
Streaming, full-duplex "realtime" voice sessions are a distinct transport and are
not provided by agentkit. Transcription and synthesis are.
:::

## Capability shortcuts

Common multimodal capabilities have builder shortcuts:

```python
agent.image_generation().web_search().web_fetch().thinking(effort="medium")
```

## A pattern: transcribe → reason → speak

```python
async def voice_turn(app, audio_path: str, conversation_id: str) -> bytes:
    text = transcribe(audio_path)
    result = await app.run(text, conversation_id=conversation_id)
    return synthesize(result.output)
```

Continue to [Safety & Moderation →](/guide/safety)
