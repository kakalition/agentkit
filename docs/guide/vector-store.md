# Vector Stores

Semantic recall ranks candidate vectors by cosine similarity. The **vector store**
is the pluggable backend that does that ranking; `vector_store_driver` selects it.
Memory recall and RAG retrieval both rank through it.

## Drivers

- `repository` (default) — an in-process store ranked with the numpy cosine scan.
  Its results are identical to the built-in recall path, so switching to it is safe.
- `sqlite_vec` — a persisted SQLite file using the optional `sqlite-vec` accelerator
  (`agentkit[vec]`); distances are computed with `vec_distance_cosine`.
- `pgvector` — a Postgres `vector` column backend (requires a Postgres
  `database_url`; the `vector` extension is created automatically).

```python
# use the optional accelerator
vector_store_driver=sqlite_vec
```

## Ranking vs. indexing

Two entry points:

- `rank(collection, vector, items)` — cosine-rank caller-supplied `(id, vector)`
  pairs. This is what memory recall and RAG use (their vectors already live in the
  database), and every driver shares the same numpy scan here, so results are
  identical regardless of driver.
- `query(collection, vector, limit=…)` — search vectors held by the store itself,
  using the backend's index when one is available (`sqlite_vec`/`pgvector`).

## The contract

Any backend implements `VectorStore`:

```python
from agentkit import VectorStore, VectorHit

class MyStore:
    async def upsert(self, collection, id, vector, *, metadata=None) -> None: ...
    async def query(self, collection, vector, *, limit=5) -> list[VectorHit]: ...
    async def rank(self, collection, vector, items, *, limit=None) -> list[VectorHit]: ...
    async def delete(self, collection, id) -> bool: ...
    async def count(self, collection) -> int: ...
```

Register it with `app.extend("vector", "mine", factory)`, or resolve the
configured store with `app.vector_store` / `app.manager("vector").driver()`.
Optional drivers raise `ConfigurationError` when their extra (or a Postgres URL)
is missing, so failures are consistent across surfaces. The active driver and its
alternatives are visible in `GET /api/studio/app` (and `app.drivers()`).
