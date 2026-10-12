# Models & Database

agentkit persists everything in a single local database (libSQL/SQLite) via
[SQLModel](https://sqlmodel.tiangolo.com) and SQLAlchemy. You get a thin,
expressive model layer for your own tables, alongside built-in repositories for
conversations, memory, knowledge, usage, and more.

## The runtime

A `Runtime` owns the engine, session factory, and the repository container:

```python
from agentkit import build_runtime, repositories

runtime = build_runtime(settings)
with repositories(runtime) as repos:
    repos.conversations.get_or_create("cli:default")
```

The `App` builds and caches a runtime for you (`app.runtime`), and
`app.repositories()` is a context manager that opens a session and commits on
exit.

## The `Model` base

Subclass `Model` to define a table with an active-record-ish surface:

```python
from sqlmodel import Field
from agentkit import Model

class Note(Model, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    pinned: bool = False
```

### Creating, reading, updating, deleting

```python
note = Note.create(text="buy milk", pinned=True)

Note.where(pinned=True).all()
Note.where(pinned=True).first()
Note.get(note.id)
Note.count()
Note.update(note.id, text="buy oat milk")
Note.delete(note.id)
```

### Querying

`where(...)` returns a chainable `Query`:

```python
(
    Note.where(pinned=True)
        .order_by("text")
        .limit(10)
        .all()
)

Note.where(pinned=True).count()
Note.paginate(page=2, per_page=15, pinned=True)
```

`paginate` returns a dict with `items`, `total`, `page`, `per_page`, and `pages`.

### The ambient session

Inside a `DB.transaction()` block, model operations join the same session and
commit together:

```python
from agentkit import DB

with DB.transaction():
    Note.create(text="a")
    Note.create(text="b")
# both committed (or both rolled back on error)
```

Outside a transaction, each operation opens (and commits) its own short session.

## Built-in repositories

`Repositories` exposes the framework's own stores, all owner-scoped:

| Repo | Access |
| --- | --- |
| `conversations` | `get_or_create`, `get`, `list`, `touch`, `fork` |
| `messages` | `append`, `next_seq`, `list`, `clear` |
| `usage` | `add`, `list`, `totals` |
| `audit` | `append`, `entries`, `verify` |
| `memories` | `add`, `update`, `forget`, `search`, `list`, `digest` |
| `knowledge` | `add`, `replace`, `clear`, `sources`, `search` |
| `feedback` | `add`, `list`, `average` |
| `schedules` | `upsert`, `list`, `get`, `set_enabled`, `remove`, `record_run` |
| `a2a` | A2A task bookkeeping |

## Extending the container

Add domain repositories by subclassing `Repositories` and registering it with the
app:

```python
from dataclasses import dataclass
from agentkit.db.repositories import Repositories

@dataclass
class AppRepositories(Repositories):
    def __post_init__(self):
        super().__post_init__()
        self.notes = NoteRepo(self.session, self.owner_id)
```

```python
app = App(name="notes", settings=settings, repos_factory=AppRepositories)
```

Every tool that receives `ctx.deps.repos` now sees `repos.notes`.

## Migrations and schema sync

Tables are created from SQLModel metadata at startup. For columns added to
existing databases, agentkit ships a lightweight drift repair:

```python
from agentkit.db.migrations import init_db, sync_missing_columns

init_db(engine)                 # create any missing tables
added = sync_missing_columns(engine)   # add drifted columns
```

For complex schema evolution, an Alembic helper is available; see
`agentkit.db.migrations`.

::: tip Prefer models for new tables
The `Model` layer is intentionally small: equality filters, first/get/create/
update/delete, counting, and pagination. For elaborate queries, drop to the
repositories or SQLAlchemy directly — the session is the same.
:::

Continue to [Conversations →](/guide/conversations)
