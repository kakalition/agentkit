# Models & Database

## Introduction

agentkit persists everything in a single local database (libSQL/SQLite) via
[SQLModel](https://sqlmodel.tiangolo.com) and SQLAlchemy. You get a thin,
expressive **async** model layer for your own tables, alongside built-in
repositories for conversations, memory, knowledge, usage, and more.

The data layer is async by default: the engine is `sqlite+aiosqlite`, every
repository method is a coroutine, and the `Model`/`Repository` helpers are awaited.
See [Async Data Layer](/guide/async) for the design and the synchronous seams.

## The runtime

A `Runtime` owns the engine, session factory, and the repository container:

```python
from agentkit import build_runtime, repositories

runtime = build_runtime(settings)
async with repositories(runtime) as repos:
    await repos.conversations.get_or_create("cli:default")
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
note = await Note.create(text="buy milk", pinned=True)

await Note.where(pinned=True).all()
await Note.where(pinned=True).first()
await Note.get(note.id)
await Note.count()
await Note.update(note.id, text="buy oat milk")
await Note.delete(note.id)
```

### Querying

`where(...)` returns a chainable `Query`:

```python
(
    await Note.where(pinned=True)
        .order_by("text")
        .limit(10)
        .all()
)

await Note.where(pinned=True).count()
await Note.paginate(page=2, per_page=15, pinned=True)
```

`paginate` returns a dict with `items`, `total`, `page`, `per_page`, and `pages`.

### The ambient session

Inside a `DB.transaction()` block, model operations join the same session and
commit together:

```python
from agentkit import DB

with DB.transaction():
    await Note.create(text="a")
    await Note.create(text="b")
# both committed (or both rolled back on error)
```

Outside a transaction, each operation opens (and commits) its own short session.

## Built-in repositories

`Repositories` exposes the framework's own stores, all owner-scoped and async:

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

await init_db(engine)                 # create any missing tables
added = await sync_missing_columns(engine)   # add drifted columns
```

For complex schema evolution, an Alembic helper is available; see
`agentkit.db.migrations`.

::: tip Prefer models for new tables
The `Model` layer is intentionally small: equality filters, first/get/create/
update/delete, counting, and pagination. For elaborate queries, drop to the
repositories or SQLAlchemy directly — the session is the same.
:::

Continue to [Conversations →](/guide/conversations)

## Drivers

### What this is, in plain English

Everything agentkit persists — conversations, memory, knowledge chunks, queued
jobs — lives in **one database**, and this page is about which *kind* of database
that is.

"Database" can mean two different things, and it is worth separating them:

- The **database engine** (SQLite, PostgreSQL, ...) is the program that actually
  stores and retrieves the rows.
- A **dialect** is the adapter that teaches the framework how to talk to a
  particular engine: how to turn a connection URL into an async driver, how to
  build the engine, and so on.

agentkit ships two dialects. The default uses SQLite (through libSQL): a single
local file with no server to install, ideal for a laptop or a small deployment.
The other targets PostgreSQL, a client/server database you would choose when
several processes share one database or you need its concurrency and operational
features.

::: tip The travel-adapter analogy
The engine is a wall socket in another country; the dialect is the travel adapter
that makes your plug fit. Same appliance (your code), different socket, different
adapter — you do not rebuild the appliance.
:::

### A runnable example

```python
import asyncio
from agentkit import App, DriverKind

async def main():
    # The engine is chosen by DATABASE_DRIVER; sqlite is the default.
    app = App()                       # DATABASE_DRIVER=sqlite (no server needed)
    print(app.manager(DriverKind.DATABASE).available())   # ['postgres', 'sqlite']

    # The dialect turns a URL into an async engine and a session factory.
    dialect = app.dialect             # == app.manager("database").driver()
    print(dialect.async_url("sqlite:///./app.db"))         # sqlite+aiosqlite:///./app.db
    print(dialect.async_url("postgresql://u:p@host/db"))   # postgresql+asyncpg://u:p@host/db

    # Tables are created from your models on startup.
    async with app.repositories() as repos:
        await repos.conversations.get_or_create("cli:default")

asyncio.run(main())
```

Switch the whole application by changing the environment variable:

```bash
DATABASE_DRIVER=sqlite     # a local file (default)
DATABASE_DRIVER=postgres   # a PostgreSQL server
```

### Built-in drivers

**Dialects — setting `DATABASE_DRIVER`**

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `sqlite` | Uses a local file via libSQL/SQLite with the async `aiosqlite` driver; enables WAL and a busy timeout | Default; local development and single-process deployments |
| `postgres` | Maps the URL to `asyncpg` and builds a PostgreSQL engine | Multiple processes sharing one database; production scale |

A dialect provides `async_url(url)` and `create_engine(url, *, auth_token=None,
echo=False)`. For remote libSQL URLs, pass an `auth_token`; for Postgres, use a
full `postgresql://` URL.

### How to select it

Selection follows the same precedence everywhere in agentkit:

1. **An explicit name in code** — `app.manager(DriverKind.DATABASE).driver("postgres")`.
2. **The setting** — `DATABASE_DRIVER`, read from the environment or a `.env` file.
3. **The default** — `sqlite`, listed first in the table above.

**Accessors:** `app.dialect` returns the configured dialect;
`app.manager(DriverKind.DATABASE)` gives the manager (`.driver()`, `.available()`,
`.configured_driver()`, `.forget()`).

Override a dialect for one app only (this never leaks into other apps or the
global registry):

```python
from agentkit import DriverKind

app.extend(DriverKind.DATABASE, "cockroach", lambda app: MyDialect())
# then select it: DATABASE_DRIVER=cockroach
```

Ship a reusable dialect to every app that imports your package with
`@register_driver`:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.DATABASE, "cockroach")
def _cockroach(app):
    return MyDialect()
```

A dialect needs no base class — only the contract's methods. See
[Contracts & Drivers](/guide/drivers) for the full catalog, precedence, and the
conformance tests every driver must pass.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `database is locked` | Two writers contend on SQLite; WAL and the busy timeout usually absorb this, but prefer one writer or move to Postgres |
| `ModuleNotFoundError: asyncpg` | `DATABASE_DRIVER=postgres` without the Postgres dependency installed |
| A remote URL is rejected | Pass the `auth_token` for a remote libSQL URL, or use a full `postgresql://` URL |
| `ValidationError` when settings load | `DATABASE_DRIVER` is not `sqlite` or `postgres` |
| Tables miss columns after an upgrade | Run `sync_missing_columns(engine)` to repair the drift |
