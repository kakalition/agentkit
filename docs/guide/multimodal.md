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

## Speech and document engines as drivers

### What these are, in plain English

Two separate jobs live on this page.

**Speech (the `audio` subsystem).** A *transcriber* turns recorded sound into
text — the same job dictation software does, often called **speech-to-text**. A
*synthesizer* does the reverse: it turns text into spoken audio, called
**text-to-speech**. Together they let an agent *listen* to a voice note and *reply
out loud*. agentkit exposes both through one object, `app.speech`.

**Documents (the `ingest` subsystem).** Most real content is not a tidy string; it
is a PDF, a Word file, an HTML page. A *document loader* reads one of those and
returns plain text the agent can reason about. `app.ingest` is that loader.

Think of a translator sitting at a front desk. A voice note arrives; the
translator writes down what it said (transcription). Your agent answers in
writing; the translator reads the answer aloud (synthesis). A document arrives in
a foreign format — a PDF — and the translator retypes it as ordinary text
(ingestion). In every case your agent only ever deals with plain text; the driver
handles the format underneath.

::: tip Two contracts, one plug each
The speech driver implements `Transcriber` (`transcribe(source) -> str`) and
`Synthesizer` (`synthesize(text) -> bytes`). The document driver implements
`DocumentLoader` (`supports(suffix) -> bool` and `load(source) -> str`). Any
object with those methods works. See [Contracts & Drivers](/guide/drivers).
:::

### A runnable example

```python
from pathlib import Path

from agentkit import App, DriverKind

app = App()   # defaults: AUDIO_DRIVER=openai, INGEST_DRIVER=default

# 1. Speech -> text through the configured speech driver (a Transcriber).
transcript = app.speech.transcribe("standup.m4a", language="en")

# 2. Text -> audio bytes through the same driver (it is also a Synthesizer).
Path("summary.mp3").write_bytes(app.speech.synthesize("Here is your summary."))

# 3. A document -> plain text through the configured ingest driver.
print(app.ingest.supports(".pdf"))       # True — the default loader reads PDFs
text = app.ingest.load("invoice.pdf")    # every page joined into one string

# 4. Switch the ingest driver: use the text-only loader directly.
from agentkit.support.kinds import IngestDriver
loader = app.manager(DriverKind.INGEST).driver(IngestDriver.TEXT)
print(loader.supports(".pdf"))           # False — this driver parses no PDFs
```

`app.speech` and `app.ingest` always expose the configured drivers; the methods
are identical no matter which driver is behind them.

### Built-in drivers

**Speech — kind `audio`, setting `AUDIO_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `openai` | Default. Transcribes with the OpenAI audio API (`whisper-1` by default) and synthesizes with `tts-1`. | You want working speech in and out with an OpenAI key and no extra setup. |

**Documents — kind `ingest`, setting `INGEST_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `default` | Default. Extracts text from plain text/Markdown/CSV/JSON/YAML and RST logs, HTML, PDF, and DOCX. | You need to read real-world documents (PDFs, Word files, web pages). |
| `text` | Text-only. Reads plain text/Markdown/CSV/JSON/etc. and raw bytes, but parses no PDF/DOCX/HTML. | You want a minimal install with no optional parsing libraries. |

::: warning Optional parser libraries
The `default` loader imports `beautifulsoup4` (HTML), `pypdf` (PDF), and
`python-docx` (DOCX) lazily. If one is missing, only that format raises
`DependencyMissing` — the other formats keep working.
:::

### Selecting a driver

Selection follows the usual precedence: an explicit name in code, then the
setting, then the default.

```bash
# .env
AUDIO_DRIVER=openai
INGEST_DRIVER=text
```

**Per app only.** `app.extend` registers a factory scoped to a single app:

```python
from agentkit import App, DriverKind
from agentkit.ingest import TextDocumentLoader

app = App()
app.extend(DriverKind.INGEST, "minimal", lambda app: TextDocumentLoader())
```

**Reusable driver.** Publish one to the global registry for everyone:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.INGEST, "csv-only")
def _csv_only(app):
    return CsvLoader()   # an object with supports(suffix) and load(source)
```

Read more on [Contracts & Drivers](/guide/drivers).

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `ConfigurationError` about OpenAI credentials | no `OPENAI_API_KEY` (or `api_key`/`client`) for the `openai` speech driver |
| `DependencyMissing: pypdf is required` | the PDF parser optional package is not installed |
| `IngestError: unsupported file type` | the suffix is outside the active loader's supported set (use the `default` driver) |
| `IngestError` about a size or scheme | the source is over `ingest_max_bytes` or uses a scheme not in `ingest_allowed_schemes` |
