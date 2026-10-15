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
