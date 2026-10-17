# Knowledge (RAG)

## Introduction

The **knowledge base** indexes your documents with embeddings and lets the agent
retrieve the most relevant passages — retrieval-augmented generation without a
separate vector service.

## Indexing documents

```python
from agentkit import KnowledgeBase

kb = KnowledgeBase()                     # uses the app/default runtime
await kb.add_directory("./docs", pattern="**/*.md")
await kb.add_file("handbook.pdf.txt")
await kb.add("Free-form note text", source="note")
await kb.add_many({"faq.md": faq_text, "policy.md": policy_text})
```

Text is chunked with overlap, embedded, and stored in the `knowledge_chunks`
table. Re-indexing a source replaces its chunks:

```python
await kb.replace("./docs/guide.md")
await kb.sources()                 # ["…/guide.md", "faq.md", ...]
await kb.count("faq.md")
await kb.clear("faq.md")
```

## Searching

```python
hits = await kb.search("how do refunds work", limit=5)
for chunk in hits:
    print(chunk.source, chunk.content[:120])

kb.format_hits(hits)         # a formatted, citation-style block
```

Search ranks by cosine similarity and appends keyword matches, so it works with or
without an embedder (see [Memory](/guide/memory#how-recall-works) for backends).

## Attaching to an agent

```python
from agentkit import AgentDefinition

class Support(AgentDefinition):
    name = "support"
    instructions = "Answer from the knowledge base."
    knowledge = kb                 # add a search_knowledge tool
    output = str

agent = Support.build()
```

Fluent equivalent:

```python
agent = (
    Agent.make("support")
    .instructions("Answer from the knowledge base.")
    .knowledge(kb)                 # add a search_knowledge tool
    .output(str)
    .build()
)
```

The `knowledge` field (fluent `.knowledge(...)`) adds a
**`search_knowledge(query, limit=5)`** tool. With `index=True` (the default) it also
lists indexed sources in the instructions so the model knows what it can search:

```python
class Support(AgentDefinition):
    name = "support"
    knowledge = kb            # a prepared KnowledgeBase
    # knowledge = "./docs"    # index a path at build time
    # knowledge = True        # use the app's default runtime
```

The `index` and `limit` sub-options have no class field, so set them in
`configure`:

```python
class Support(AgentDefinition):
    name = "support"

    def configure(self, agent):
        return agent.knowledge(kb, limit=8, index=False)
```

## Choosing a chunk size

```python
kb = KnowledgeBase(chunk_chars=1200, overlap=200)
```

Larger chunks carry more context; smaller chunks retrieve more precisely. The
defaults (1200 chars, 200 overlap) suit prose documentation.

## From the CLI

```bash
agentkit knowledge add ./docs
agentkit knowledge add-text "Refunds take 5 days" --source policy
agentkit knowledge search "refund policy"
agentkit knowledge list
```

## Ingesting documents and URLs

`KnowledgeBase.add_file` extracts text from the document format (not just plain
text) and `add_url` fetches and extracts a web page. Both are guarded by
`INGEST_MAX_BYTES` and `INGEST_ALLOWED_SCHEMES` (and an SSRF egress check).

```bash
agentkit knowledge add-file report.pdf
agentkit knowledge add-file brief.docx --source brief
agentkit knowledge add-url https://example.com/post
```

Supported formats: plain text/markdown/CSV/JSON, HTML (`beautifulsoup4`), PDF
(`pypdf`), and DOCX (`python-docx`). Parsers are imported lazily, so a missing
optional library only affects its own format. `agentkit.ingest.extract_text`
works on a path; `fetch_url` on a URL.

::: tip Knowledge vs. memory
Use **knowledge** for corpora that change rarely and are retrieved by meaning.
Use [memory](/guide/memory) for a few mutable facts about the owner. Both can be
attached to the same agent.
:::

Continue to [Context Compaction →](/guide/compaction)

## Drivers

### What this is, in plain English

"RAG" (retrieval-augmented generation) is a grand name for a simple idea: before
the model answers, look up the parts of your own documents that are relevant and
put them in front of it, so it answers from your material instead of guessing. A
**knowledge base** is the searchable index of those documents.

Three steps happen, and each is a separate, swappable driver:

1. **Chunking** — documents are long and the model can only read so much at once,
   so each document is cut into smaller passages ("chunks"). The *chunker* decides
   where the cuts go.
2. **Retrieval** — given the user's question, the *retriever* finds the chunks that
   look most relevant, usually by comparing embeddings (the meaning-numbers from
   the [Memory](/guide/memory) page).
3. **Reranking** — the *reranker* takes those candidates and may reorder them by a
   finer signal before they are shown to the model.

::: tip The book-search analogy
Chunking is tearing a textbook into index cards. Retrieval is pulling the cards
whose topics match your question. Reranking is skimming those cards and putting
the single most useful one on top before you read it out.
:::

Retrieval ranks by cosine similarity of embeddings and also appends keyword
matches, so it still works — less precisely — when no embedder is configured.

### A runnable example

```python
import asyncio
from agentkit import App, DriverKind, KnowledgeBase

async def main():
    # Build the knowledge base; it uses the app's default runtime.
    app = App()                       # CHUNKER/RETRIEVER/RERANKER_DRIVER read here
    kb = KnowledgeBase(app)
    print(app.chunker, app.retriever, app.reranker)   # the three configured drivers

    # Index a folder of Markdown documents (chunked, embedded, stored).
    await kb.add_directory("./docs")

    # Retrieve the passages most relevant to a question.
    hits = await kb.search("how do refunds work", limit=5)
    print(kb.format_hits(hits))       # a citation-style block for the prompt

    # Use a different chunker for one call by naming it explicitly.
    fixed = app.manager(DriverKind.CHUNKER).driver("fixed")
    print(fixed.chunk("a long document ..."))

asyncio.run(main())
```

Switch the whole pipeline by changing the environment variables:

```bash
CHUNKER_DRIVER=fixed        # cut on length instead of meaning
RETRIEVER_DRIVER=memory     # a lightweight in-process substring retriever
RERANKER_DRIVER=lexical     # reorder candidates by query-word overlap
```

### Built-in drivers

**Chunkers — setting `CHUNKER_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `semantic` | Splits on semantic boundaries (paragraphs, sentences, words) using `semantic-text-splitter` | Default; prose and documentation |
| `fixed` | Slices every N characters with overlap; no extra dependency | When you cannot ship the Rust splitter, or want uniform windows |

**Retrievers — setting `RETRIEVER_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `repository` | Searches the indexed chunks stored in the agent database | Default; a durable, persistent index |
| `memory` | Simple substring search over chunks held in the process | Tests, ephemeral agents, no database |

**Rerankers — setting `RERANKER_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `identity` | Leaves the retriever's order unchanged | Default; retrieval ordering is already good |
| `lexical` | Reorders candidates by how many query words appear in each chunk | A quick keyword boost without a model |

The contracts are small: a chunker provides `chunk(text, **options)`, a retriever
provides `search(query, *, limit=5, source=None)` (async), and a reranker provides
`rerank(query, hits, **options)`.

### How to select it

Selection follows the same precedence everywhere in agentkit:

1. **An explicit name in code** — `app.manager(DriverKind.CHUNKER).driver("fixed")`.
2. **The setting** — `CHUNKER_DRIVER`, `RETRIEVER_DRIVER`, or `RERANKER_DRIVER`,
   read from the environment or a `.env` file.
3. **The default** — `semantic`, `repository`, and `identity`, listed first above.

**Accessors:** `app.chunker`, `app.retriever`, and `app.reranker` return the
configured drivers; the managers are `DriverKind.CHUNKER`, `DriverKind.RETRIEVER`,
and `DriverKind.RERANKER`.

Override a driver for one app only (this never leaks into other apps or the global
registry):

```python
from agentkit import DriverKind

app.extend(DriverKind.CHUNKER, "paragraph", lambda app: MyChunker(app))
# then select it: CHUNKER_DRIVER=paragraph
```

Ship a reusable driver to every app that imports your package with
`@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.CHUNKER, "paragraph")
def _paragraph(app):
    return MyChunker(app)
```

A driver needs no base class — only the contract's methods. See
[Contracts & Drivers](/guide/drivers) for the full catalog, precedence, and the
conformance tests every driver must pass.

### Drivers

Writing and reading each resolve a driver: `chunker_driver` (default `semantic`)
splits text, `retriever_driver` (default `repository`) finds candidates, and
`reranker_driver` (default `identity`) reorders them. Document loading uses
`ingest_driver`. Semantic ranking runs through the configured
[vector store](/guide/vector-store) (`vector_store_driver`); the default
`repository` driver reproduces the built-in numpy cosine scan exactly.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Search returns nothing | Nothing indexed for that source, or no embedder and no literal keyword match |
| Results ignore meaning | No embedder configured, so retrieval fell back to keyword matching |
| Re-indexing duplicates content | Use `kb.replace(source)` instead of adding the source again |
| `ValidationError` when settings load | A `*_DRIVER` value is not a valid driver name |
| `ConfigurationError: unknown chunker driver` | The selected driver is not registered — check spelling, or `app.extend(...)` it first |
