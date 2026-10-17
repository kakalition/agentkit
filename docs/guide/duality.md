# Class & functional duality

agentkit follows Laravel's model: **closures are the quick, local form; classes
are the reusable, scalable form — and neither is deprecated.** At every seam both
forms are first-class and normalize to the same internal abstraction, so DI,
registration, and behaviour are identical either way.

Classes are *recommended* for reusable or long-lived units (a channel you ship, a
toolkit you install everywhere); a closure is equally valid for a one-off. The
scaffold stays class-based, and nothing here removes an existing functional API.

## The one normalization layer

Every seam accepts:

| Input | Example |
| --- | --- |
| closure / callable | `app.on("turn.end", lambda ev: ...)` |
| class | `app.tool(SearchNotes)`, `app.middleware(Timing)` |
| instance | `app.listeners([AuditListener()])` |
| `"module:attr"` string spec | `app.commands(["myapp.commands:Greet"])` |

`foundation.callable.normalize` resolves each input to a :class:`Resolved`
(`.callable` / `.instance` / `.origin`), and `Container.wrap(target, protocol=…)`
returns the invocable a seam expects. A bad string spec is logged and skipped —
never fatal (the same policy as provider discovery).

```python
from agentkit import normalize, invoke

normalize(AuditListener).instance          # class -> instantiated instance
normalize(lambda ev: None).callable        # closure -> the function itself
normalize("myapp.listeners:Audit")         # imported lazily, then as above
```

Protocols name the seam (`listener`, `channel`, `command`, `middleware`,
`job`); the normalizer picks the instance method (`handle`, `__call__`) when the
resolved object is not itself callable.

## Container injection (`Container.call`)

`Container.call(target, params=None)` is Laravel's `Container::call`: it invokes a
callable, injecting the typed parameters that were not supplied. Explicit
`params`/keyword arguments always win; scalars (`str`, `int`, …) are never
fabricated; an unresolvable required parameter raises `BindingError`.

```python
container.call(handler)                 # inject typed params
container.call(handler, {"name": "x"})  # explicit wins
```

`Container.call` stays **synchronous** and returns awaitables untouched — the
caller awaits.

## DI scope

Only framework-owned parameters are injected:

- `Command.handle` and `Channel.handle` — yes.
- A seam unit's `__init__` (listener, channel, command, middleware) — yes, with a
  plain-constructor fallback.
- **Tool parameters — never.** A tool's schema belongs to PydanticAI; the
  container does not touch it.

## Seam by seam

### Events & listeners

```python
app.on("turn.end", lambda ev: audit(ev.conversation_id))   # closure
app.on(TurnEnded, RecordTurnEnded)                          # class
app.listeners([AuditListener(), "myapp.listeners:Notify"])  # instance + string
app.on("*", log_everything)                                 # wildcard
```

`app.on` returns the `App`, so it chains. A listener may register by event class
or by the legacy string name; both fire (dual dispatch).

### Tools & toolkits

```python
app.tool(current_time)                       # function
app.tool(SearchNotes)                        # Tool class
app.tool(SearchNotes())                      # Tool instance

attach_usage(agent)                          # functional toolkit helper
UsageToolkit().install(agent)                # class toolkit (delegates to the helper)
```

`agentkit.toolkits.attach_*` are the functional face of the built-in `Toolkit`
classes; both install exactly the same tools.

### Drivers

```python
@register_driver(DriverKind.CACHE, "redis")
class RedisCacheDriver(Driver): ...

@register_driver(DriverKind.CACHE, "pantry")
def pantry_cache(app): return PantryCache(app.settings)

app.extend("cache", "local", lambda app: LocalCache())   # app-scoped closure
```

### Commands

```python
app.commands([("greet {name} {--loud}", lambda name, loud=False: hello(name))])  # closure
app.commands([GreetCommand])                                                    # class
```

### Channels

```python
app.channel("slack", SlackChannel)               # Channel class
app.channel("web", lambda app: web_service(app)) # factory
```

### Middleware

```python
app.middleware(timing)            # function middleware(turn, call_next)
app.middleware(TimingMiddleware)  # Middleware class (instantiated)
app.middleware(MiddlewareGroup("web", [auth, logging]))
```

### Jobs

```python
await app.dispatch(EmailDigest())       # Job class/instance
await app.dispatch(lambda: resync())    # closure job (runs inline)
```

A closure cannot be serialized onto the durable queue, so closure jobs always run
in-process even when `queue_enabled` is set; use a `Job` subclass to queue.

### Validation

Three forms compile to one predicate: string sugar (`"min:3"`), a callable
predicate (`Rule.min(3)`), or a `ValidationRule` object.

### Gate

```python
app.gate.define("publish", lambda actor, subject: actor.id == owner)  # closure
app.policies([NotePolicy])                                           # Policy class
```

### Agents

The declarative `AgentDefinition` (class) and the fluent `Agent.make(...)` builder
(functional) express the same agent — and `AgentDefinition.tools` accepts `Tool`
classes too.
