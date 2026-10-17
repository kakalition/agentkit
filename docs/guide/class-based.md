# Laravel → agentkit

agentkit's framework layer is deliberately Laravel-shaped, and — like the rest of
the project — **class-based**. This page is the concept map: what each Laravel
idea is called here, the class you extend, and where to read more. Every entry is
a superset of what came before; nothing here removes the older functional API.

## Concept map

| Laravel | agentkit | Class to extend / use |
| --- | --- | --- |
| Service provider | Service provider | `Provider` |
| Artisan command | Command | `Command` (`signature`, `handle()`) |
| Route/console kernel | Console kernel | `foundation.console.Kernel` |
| Eloquent model | Model | `Model` (`has_many`/`belongs_to`/…) |
| Casts / accessors | Casts / accessors | `casts = {...}`, `Attribute` |
| Migration | Migration | `Migration`, `Schema` |
| Seeder | Seeder | `Seeder`, `SeederRunner` |
| Factory | Factory | `Factory`, `HasFactory` |
| Collection | Collection | `Collection`, `CursorCollection` |
| Paginator | Paginator | `LengthAwarePaginator`, `Paginator` |
| Validation rule | Validation rule | `ValidationRule`, `Validator`, `Rule` |
| Gate / Policy | Gate / Policy | `Gate`, `Policy` |
| Event / Listener | Event / Listener | `Listener` (event classes like `TurnEnded`) |
| Middleware | Middleware | `Middleware`, `MiddlewareGroup` |
| Job / Queue | Job / Queue | `Job` (+ `chain`, `batch`, `Job.middleware()`) |
| Notification | Notification | `Notification`, `ShouldQueue` |
| Form Request | Validation | `Validator`, `Rule.unique(...)` |
| Blade/service container | Container + facades | `Container`, `Facade` |
| `php artisan make:*` | `agentkit make:*` | generators |
| PHPUnit TestCase | TestCase | `agentkit.testing.TestCase`, fakes |

## The agent is a class

Where Laravel has no single "agent", agentkit makes the agent a declarative class.
See [The Agent Builder](/guide/agents#class-based-definition-recommended):

```python
class Assistant(AgentDefinition):
    name = "assistant"
    instructions = "You are a concise, helpful assistant."
    tools = [current_time]
    full = True
    output = str

agent = Assistant.build()          # → pydantic_ai.Agent
```

## Commands are classes

```python
class MakeReport(Command):
    signature = "reports:make {name} {--force}"
    description = "Build a report."

    def handle(self, name: str, force: bool = False) -> None:
        self.info(f"building {name}")
```

`handle`'s typed parameters are injected from the container (declare `app: App`)
and from the CLI. The built-in `agentkit` commands are themselves `Command`
subclasses; their names and flags are unchanged.

## Models are Eloquent-ish

```python
class Post(Model, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = None
    casts = {"meta": "json"}
    comments = has_many("Comment", foreign_key="post_id")

    user = belongs_to("User")

    @classmethod
    def scope_published(cls, query):
        return query.where(published=True)
```

`Model.where(...).all()` returns a `Collection`; `paginate()` returns a
`LengthAwarePaginator` that still indexes like the legacy dict. Soft deletes,
observers, global scopes, factories, seeders, and migrations are all available —
see [Models & Repositories](/guide/repositories) and [Database](/guide/database).

## Authorization

```python
class PostPolicy(Policy):
    model = Post
    def update(self, actor, post):
        return post.owner_id == actor.id

Gate.policy(Post, PostPolicy)
Gate.allows("update", post, actor=actor)
```

Policies are discovered from `app/Policies/`, registered by providers via
`policies()`, and queried with the `can()` / `authorize()` / `policy()` helpers.
The existing tool-RBAC `ToolPolicy` is bridged through `Gate.tool_policy(...)`.

## Events, listeners, middleware

```python
class AuditTurn(Listener):
    event = TurnEnded
    def handle(self, event):
        ...
```

Event classes (`TurnEnded`, `ToolStarted`, …) dual-dispatch with the legacy string
names. Middleware can be grouped and aliased: `app.middleware(MiddlewareGroup("web", [...]))`
then `app.middleware("web")`.

## Jobs, chains, batches

```python
await chain(SyncNotes(), Reindex()).then(on_done).dispatch(app)
await batch([SyncNotes(), SyncDocs()]).catch(on_error).dispatch(app)
```

`Job` supports `middleware()` and a `failed(app, error)` hook. Notifications mix in
`ShouldQueue` to deliver through the durable queue.

## Testing

```python
from agentkit.testing import TestCase, fake_queue, freeze_time

class TestReminders(TestCase):
    async def test_queued(self):
        await self.boot()
        queue = self.fake_queue()
        self.app.notify(ReminderDue("stretch"))
        queue.assert_pushed(ReminderJob)
```

`agentkit.testing` ships `FakeQueue`, `FakeNotifier`, `FakeCache`, `FakeStorage`,
`fake_events`, `make` / `create` factory helpers, Gate assertions
(`assert_allows` / `assert_denies`), and `freeze_time` / `travel`.

## Drivers can be classes

The global driver registry accepts either a `factory(app)` function or a `Driver`
subclass:

```python
@register_driver(DriverKind.CACHE, "redis")
class RedisCacheDriver(Driver):
    def build(self):
        return RedisCache(self.app.settings.redis_url)
```

See [Contracts & Drivers](/guide/drivers).

## Removed functional forms

agentkit is class-based end to end. These functional/imperative forms are **gone
from the public API**; use the class instead.

| Removed | Use instead |
| --- | --- |
| `Agent.make(...).tool(...).full().build()` fluent builder | `AgentDefinition` class attributes (+ `configure`/`define` hooks) |
| `attach_*` toolkit functions (`attach_database`, …) | `Toolkit` subclasses (`DatabaseToolkit`, `SchedulerToolkit`, …) |
| Factory-based channels (`def x_channel(app)`) | `Channel` subclasses under `app/Channels/` |
| `app.on(name, listener)` / inline-lambda listeners | `Listener` subclasses registered with `app.listeners([...])` |
| Built-in CLI command functions (`@app.command`) | `Command` subclasses compiled into the Click kernel |
| Public `attach_*` capability bindings (`attach_memory`, …) | `Capability` classes (`MemoryCapability`, `TasksCapability`, `LearningCapability`, `ArtifactsCapability`, `TeamLedgerCapability`, `CodeExecutorCapability`, `ComputerCapability`, `AgentsCapability`) |
| Driver factory functions (`@register_driver(...)` on a `def`) | `Driver` subclasses (the registry rejects callables) |

Plain **functions are still accepted as tools** — a tool *is* a callable
underneath — but agents, toolkits, channels, listeners, commands, models, and
policies are declared as classes.

