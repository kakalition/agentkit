# Search

## Introduction

agentkit indexes conversation history so the agent (and the operator UI) can
search across *every* past session, not just the current one. Search is a normal
subsystem: a contract, a `Manager`, drivers selected by `search_driver`, and a
conformance test.

| Driver | Default | What it does |
| --- | --- | --- |
| `fts` | ✅ | SQLite **FTS5** over `messages`; falls back to `LIKE` when FTS5 is unavailable |
| `scan` | | a bounded linear scan (the historical behavior) |

The `fts` index is an external-content FTS5 table (`messages_fts`) kept in sync by
triggers, created during schema sync. If your SQLite build lacks FTS5 the
repository transparently falls back to `LIKE`, so nothing breaks.

## Selecting a driver

```bash
SEARCH_DRIVER=fts            # fts | scan
```

```python
from agentkit import App

app = App(...)
app.extend("search", "custom", lambda app: MyIndex())
```

`app.search` resolves the configured index.

## The tool surface

The history toolkit exposes `search_history` and its alias `search_sessions` to
the agent (enable with `.history()` or `.native()`):

```text
search_history(query="zebra", limit=10)
→ [{"conversation_id": "telegram:42", "text": "the launch codename is zebra nine"}]
```

## The operator UI

The web UI includes a **Search** page (and `GET /api/search?q=...`) that runs the
same driver over the owner's conversations.

## The contract

```python
from agentkit.contracts import SearchIndex, SearchHit
```

A driver implements three methods; the per-request repositories are passed in, so
one driver instance serves every session:

```python
async def search(self, repos, query, *, limit=10) -> list[SearchHit]: ...
async def index(self, repos, conversation_id, payloads) -> int: ...
async def remove(self, repos, conversation_id) -> int: ...
```

`fts` keeps the index in sync via triggers, so its `index`/`remove` are
book-keeping; `scan` has nothing to maintain.
