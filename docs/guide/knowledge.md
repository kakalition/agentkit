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
agent = (
    Agent.make("support")
    .instructions("Answer from the knowledge base.")
    .knowledge(kb)                 # add a search_knowledge tool
    .output(str)
    .build()
)
```

`.knowledge(...)` adds a **`search_knowledge(query, limit=5)`** tool. With
`index=True` (the default) it also lists indexed sources in the instructions so the
model knows what it can search:

```python
agent.knowledge(kb, index=False)      # tool only, no source listing
agent.knowledge(path="./docs")        # index a path at build time
agent.knowledge(kb, limit=8)          # default result limit
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

::: tip Knowledge vs. memory
Use **knowledge** for corpora that change rarely and are retrieved by meaning.
Use [memory](/guide/memory) for a few mutable facts about the owner. Both can be
attached to the same agent.
:::

Continue to [Context Compaction →](/guide/compaction)
