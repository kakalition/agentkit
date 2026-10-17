# Scheduling & Durability

## Introduction

Agents do work on a clock and must survive restarts. agentkit provides durable
cron *and* one-off jobs, plus DBOS-backed workflows for multi-step processes.

## Defining a task

A task is a plain callable registered under a name:

```python
from agentkit import Schedule
from agentkit.deps import Deps

@Schedule.task("digest")
def digest(period: str = "week") -> None:
    """Send a periodic digest."""
    ...
```

Register it during a provider's `boot()` (so importing the provider stays
side-effect free):

```python
class SchedulerProvider(Provider):
    def boot(self, app):
        from notes.services import digest  # noqa: F401 — registers the task
```

## Cron and one-off jobs

Register jobs with the **fluent scheduler** (Laravel-style):

```python
app.schedule("check_reminders").every_minute()
app.schedule("digest").name("weekly-digest").daily_at("08:00").args(period="week")
app.schedule("welcome").at(datetime(2030, 1, 1, 9, 0))     # one-off
```

Available frequencies: `.every_minute()`, `.every_five_minutes()`,
`.every_ten_minutes()`, `.every_fifteen_minutes()`, `.every_thirty_minutes()`,
`.hourly(minute=0)`, `.daily(hour, minute)`, `.daily_at("08:00")`,
`.weekly(day, hour, minute)`, `.weekly_on(day, "09:00")`, `.monthly(day, hour, minute)`,
`.monthly_on(day, "09:00")`, `.cron("0 8 * * 1")`, and `.at(datetime)` for one-offs.
Chain `.name("…")`, `.args(...)`, and `.enabled(False)`.

Declare schedules in a provider's `register`/`boot`; the app persists them at the
end of boot.

Or register specs directly (equivalent):

```python
app.schedules([
    {"name": "weekly-digest", "cron": "0 8 * * 1", "task": "digest", "args": {"period": "week"}},
    {"name": "welcome",       "when": "2030-01-01T09:00", "task": "welcome"},
])
```

And imperatively at runtime (the `Schedule` facade):

```python
from agentkit import Schedule

await Schedule.cron("weekly-digest", "0 8 * * 1", "digest", args={"period": "week"})
await Schedule.once("welcome", "2030-01-01T09:00", "welcome")
```

## Managing jobs

```python
await Schedule.list()
await Schedule.enable("weekly-digest")
await Schedule.disable("weekly-digest")
await Schedule.remove("weekly-digest")
Schedule.run_due()      # run anything due right now (catch-up)
```

```bash
agentkit schedule:list
```

## How durability works

- Jobs are **stored in the database**, so they survive restarts.
- The scheduler is a DBOS workflow that ticks and runs due jobs reliably.
- `init_scheduler(settings, repos_factory=...)` is called by `agentkit serve`; in a
  custom entry point, call it after `app.boot()`:

```python
app.boot()
from agentkit import scheduler
scheduler.init_scheduler(app.settings, repos_factory=app.repos_factory)
app.serve()
```

## Built-in durable tasks

`FullStackProvider` registers two built-in tasks and schedules them daily:

| Task | Scheduled by | Purpose |
| --- | --- | --- |
| `memory:consolidate` | `MEMORY_ENABLED` | dedupe / summarize / prune memory |
| `learning:reflect` | `LEARNING_ENABLED` | the [self-learning](/guide/self-learning) reflect loop |

Both are idempotent (`register_consolidate_task` / `register_reflect_task`) and
never raise when unconfigured.

## Workflows

For multi-step processes with retries and compensation, use DBOS workflows:

```python
from agentkit import durability

durability.init(queues=["default"])

@durability.workflow()
async def onboard(user_id: str) -> None:
    await send_welcome(user_id)      # each step is durable & retried
    await create_workspace(user_id)
```

Failed workflows land in a `failed_workflows` dead-letter view you can inspect in
the web UI.

## Catching up

Long jobs can drift. `Schedule.run_due()` runs everything currently due, which is
handy after downtime or in a startup hook.

::: tip Keep tasks idempotent
Schedules guarantee *at-least-once* execution. Make a task safe to run twice
(upserts, idempotency keys) rather than assuming exactly-once.
:::

Continue to [Budgets & Limits →](/guide/budgets)

## Drivers

### What a scheduler and durability driver are, in plain English

Two related ideas run this page, and neither needs any background:

- A **scheduler** is the thing that decides *when* your code runs. Think of it as
  an alarm clock: you say "run the digest every Monday at 08:00", and the clock
  wakes the task up at the right moment.
- **Durability** (often called **durable execution**) means the work *survives a
  crash or restart*. Imagine a board game with a "save game" button: if the
  power goes out mid-turn, you reload and continue instead of starting over. A
  durable system records each step, so a multi-step job that is interrupted
  resumes where it stopped rather than repeating everything or losing progress.

A plane analogy helps separate them: the scheduler is the **departure board**
(it knows what leaves and when), and durability is the **flight recorder plus
checkpoint system** (it makes sure a flight that was interrupted can be picked
up again). You can use either one on its own, but together they are how an agent
keeps running jobs on a real server.

Both are **drivers**: pluggable implementations you pick with one setting. The
rest of this page is about the built-in ones, how to choose, and how to add your
own.

### A runnable example

```python
from agentkit import App, DriverKind, Schedule

app = App()   # reads SCHEDULER_DRIVER / DURABILITY_DRIVER from the env / .env

@Schedule.task("digest")               # 1. register a plain callable under a name
def digest(period: str = "week") -> None:
    print(f"sending the {period} digest")

# 2. schedule it with the fluent scheduler (default driver: dbos)
app.schedule("digest").name("weekly-digest").weekly_on("mon", "08:00").args(period="week")

# 3. inspect which driver the app actually resolved, and what else is available
print(app.manager(DriverKind.SCHEDULER).configured_driver())   # -> "dbos"
print(app.manager(DriverKind.SCHEDULER).available())          # -> ["dbos", "memory"]
print(app.manager(DriverKind.DURABILITY).configured_driver()) # -> "dbos"

# 4. switch drivers without touching code — set an env var and rebuild the app
#    SCHEDULER_DRIVER=memory   (in-process, for tests / ephemeral runs)
#    DURABILITY_DRIVER=temporal (needs the optional extra; see the warning below)
```

### Built-in drivers

**Scheduler** (`SCHEDULER_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `dbos` (default) | Stores jobs in the database and runs them through a DBOS cron workflow that ticks every minute, giving each run a deterministic id so it fires at most once per due minute, even across restarts. | Anything real: production, or any job you do not want to lose when the process restarts. |
| `memory` | Keeps jobs in a Python dictionary inside the running process; nothing is written to the database. | Tests, notebooks, and throwaway runs where persistence does not matter. |

**Durability** (`DURABILITY_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `dbos` (default) | DBOS Transact: durable workflows and steps, queues, and schedules, backed by a local SQLite system database. Steps are retried and a workflow interrupted by a crash resumes from its last completed step. | Multi-step processes (`@durability.workflow()`) that must not lose progress. |
| `temporal` | An optional driver (needs the `agentkit[temporal]` extra) that connects to a Temporal cluster and submits workflows by name; schedules map to Temporal schedules. Missing `temporalio` raises a `ConfigurationError` naming the extra. | When you already run Temporal and want its durability for the same workflows. |

The durability driver is reached through `app.durability`. The DBOS driver is
what keeps the exactly-once guarantees described above; the scheduler's tick
workflow is itself a durable DBOS workflow.

::: warning `temporal` needs a worker
Temporal submits workflows by their fully-qualified name, so the target worker must
register the workflow classes (`temporalio.workflow.defn`) on the task queue;
agentkit's DBOS-style decorators do not register a workflow with a Temporal worker.
:::

### How to select a driver

Set the environment variable (in the shell, `.env`, or your process manager):

```bash
SCHEDULER_DRIVER=dbos      # dbos | memory
DURABILITY_DRIVER=dbos     # dbos | temporal (needs the temporal extra)
```

Selection follows the standard driver precedence:

1. An **explicit name passed in code** — `app.manager(DriverKind.SCHEDULER).driver("memory")`.
2. The **setting** — `SCHEDULER_DRIVER` / `DURABILITY_DRIVER` from the environment or `.env`.
3. The **default** — `dbos` for both.

You can confirm what is active with `agentkit inspect` (it prints a
`drivers: scheduler=…, durability=…` line) or by reading
`app.manager(kind).configured_driver()`.

### Override it just for your app

Use `app.extend(...)` to register a driver that is scoped to this application
only (it never leaks into other apps or the global registry):

```python
from agentkit import DriverKind

app.extend(DriverKind.SCHEDULER, "memory", lambda app: MemoryScheduler(app))
app.extend(DriverKind.DURABILITY, "custom", lambda app: MyDurability(app))
```

Then select it with `SCHEDULER_DRIVER=memory` (or `DURABILITY_DRIVER=custom`).

### Ship a reusable driver

To publish a driver for everyone, register it in the global registry. A driver
needs no base class — it only needs the contract's methods:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.SCHEDULER, "database")
def _database_scheduler(app):
    return DatabaseScheduler(app)
```

If your driver needs a heavy package, import it *inside* the factory and raise a
`ConfigurationError` naming the extra, so an unconfigured install still starts.
See [Contracts & Drivers](/guide/drivers) for the full contract and the
conformance-test approach.

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `ConfigurationError` naming `temporalio` or an extra | You selected `DURABILITY_DRIVER=temporal`; it needs `pip install agentkit[temporal]`. |
| Jobs silently disappear after a restart | You selected `SCHEDULER_DRIVER=memory`, which is in-process only. |
| `ConfigurationError: unknown scheduler driver 'x'` | The driver name is misspelled or not registered — register it with `app.extend(...)` or `@register_driver` first. |
| A changed setting had no effect | The manager caches drivers per app; call `app.manager(DriverKind.SCHEDULER).forget()` or restart the process. |
