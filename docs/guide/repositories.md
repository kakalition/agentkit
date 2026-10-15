# Models & Repositories

## Introduction

Persist your data with a `Model` (the table) and a `Repository` (the data-access
layer). Declare the model and you inherit the whole CRUD surface — you only write
the queries that are special.

Both layers are **async**: repository methods and `Model`/`RepositoryQuery`
terminals are coroutines, so use `await` (and `async def` for your own methods).
See [Async Data Layer](/guide/async).

## A model

```python
from sqlmodel import Field
from agentkit import Model

class Reminder(Model, table=True):
    __tablename__ = "reminders"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)     # owner scoping (optional)
    text: str
    due_at: datetime
```

`Model` is agentkit's thin layer over SQLModel. If a field named `owner_id`
exists, the repository scopes every query to the current owner.

## A repository

```python
from agentkit import Repository

class ReminderRepo(Repository[Reminder]):
    model = Reminder                       # that's it — CRUD is inherited

    async def due(self, when: datetime) -> list[Reminder]:   # add only what's special
        return await self.where(delivered=False).all()
```

You now have, for free:

```python
await repo.create(text="stretch", due_at=tomorrow)   # also repo.add(...)
await repo.get(id); await repo.find(id)              # find() raises NotFound
await repo.all(order_by="due_at"); await repo.first(text="x")
await repo.where(pinned=True).order_by("id").limit(5).all()
await repo.update(id, text="new"); await repo.delete(id)
await repo.update_or_create(defaults={...}, text="x")
await repo.count(); await repo.paginate(page=2, per_page=15)
```

`where(...)` returns a chainable `RepositoryQuery` with `where`, `order_by`,
`limit`, `offset`, `all`, `first`, `count`, `paginate`, and `delete`.

## Attaching repositories

Declare them on the container and the base attaches them for you:

```python
from agentkit.db.repositories import Repositories

class AppRepositories(Repositories):
    repositories = {"reminders": ReminderRepo, "notes": NoteRepo}
```

```python
app = App(name="elle", settings=Settings, repos_factory=AppRepositories)
```

Tools and services reach them through the session:

```python
async def remind_me(ctx, text: str, when: str) -> str:
    reminder = await ctx.deps.repos.reminders.create(text=text, due_at=parse_when(when))
    return f"set #{reminder.id}"
```

::: tip Repositories vs. active-record
Use `Repository` when you are inside a request/turn (you have `ctx.deps.repos`).
The active-record [`Model`](/guide/database) classmethods (`Model.create(...)`) are
handy for one-offs and scripts, resolving the current app automatically.
:::

## Built-in repositories

The base `Repositories` already exposes `conversations`, `messages`, `usage`,
`audit`, `memories`, `knowledge`, `feedback`, `schedules`, and `a2a` — see
[Models & Database](/guide/database) for the full list.

## Migrations

Tables are created from SQLModel metadata at startup; drifted columns are repaired
with `sync_missing_columns(engine)`. See [Models & Database](/guide/database#migrations-and-schema-sync).
