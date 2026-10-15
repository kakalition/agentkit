# Native Tools

## Introduction

agentkit's capabilities are **first-class, agent-callable tools**. Database rows,
scheduled tasks, background jobs, notifications, conversation history, usage,
knowledge writes, and skill authoring can all be driven by the model itself —
not just your code.

Native tools are **opt-out** (each capability has a settings flag, on by default),
but they are **safe by construction**:

- **deny-by-default allow-lists** — no model, task, or job is reachable unless your
  app names it;
- **approval-gated writes** — every mutating tool is registered with
  `requires_approval=True`, so it defers to your approver;
- **owner scoping** — reads and writes go through owner-scoped repositories;
- **auditing** — writes append to the audit log and emit lifecycle events.

::: tip Native tools vs. building your own
Reach for a native toolkit when the capability already exists in agentkit. Write a
plain `@agent.tool` when the behaviour is app-specific.
:::

## Enabling toolkits

`Agent.full()` attaches every settings-enabled toolkit. You can also opt in one
capability at a time:

```python
from agentkit import Agent

agent = (
    Agent.make("assistant")
    .instructions("Be helpful.")
    .database({"note": Note})      # CRUD over an allow-list of models
    .scheduler(["sync_notes"])     # manage schedules over allow-listed tasks
    .queue({"sync": SyncNotes})    # enqueue allow-listed jobs
    .notifications()               # notify / notify_me
    .history()                     # list / search / read conversations
    .usage()                       # usage + audit trail (read-only)
    .knowledge_admin()             # index / replace / forget documents
    .skill_authoring()             # write SKILL.md files
    .output(str)
    .build()
)
```

`.native(enabled=None, *, models, tasks, jobs)` attaches the whole set (all
settings-enabled toolkits by default). Attaching a toolkit twice is a no-op.

Each toolkit is gated by a settings flag:

| Toolkit | Flag | Attaches |
| --- | --- | --- |
| `database` | `DB_TOOLS_ENABLED` | `db_*` |
| `scheduler` | `SCHEDULER_TOOLS_ENABLED` | `schedule_*` |
| `queue` | `QUEUE_TOOLS_ENABLED` | `enqueue_*`, `queue_status`, … |
| `notifications` | `NOTIFICATION_TOOLS_ENABLED` | `notify`, `notify_me` |
| `history` | `HISTORY_TOOLS_ENABLED` | `list_conversations`, … |
| `usage` | `USAGE_TOOLS_ENABLED` | `usage_summary`, `audit_trail`, … |
| `knowledge_admin` | `KNOWLEDGE_ADMIN_ENABLED` | `index_document`, … |
| `skills_admin` | `SKILL_AUTHORING_ENABLED` | `save_skill`, `update_skill` |

## The allow-lists

Native tools can only touch what your app explicitly exposes, recorded on the
builder or on the `App`:

```python
from agentkit import App

app = App(name="assistant")
app.models({"note": Note})               # database model allow-list
app.agent_tasks(["sync_notes", "digest"])  # scheduler + queue task allow-list
app.agent_jobs({"sync": SyncNotes})      # queue job allow-list
```

Builder-provided mappings are merged with the app-level ones, so the app (not the
model) always decides what is reachable.

::: warning `App.models` is overloaded
`App.models({...})` (a mapping) records the database allow-list. `App.models(fn)`
(a callable) sets the per-turn model resolver — a different feature. Pass a mapping
for allow-lists.
:::

## The toolkits

### Database

CRUD over an allow-list of `Model` or `Repository` subclasses. Reads are always
available; writes require approval.

| Tool | Approval | Args |
| --- | --- | --- |
| `db_list_models` | no | — |
| `db_describe` | no | `model` |
| `db_find` | no | `model`, `filters={}`, `limit=20` |
| `db_get` | no | `model`, `id` |
| `db_count` | no | `model`, `filters={}` |
| `db_create` | **yes** | `model`, `values` |
| `db_update` | **yes** | `model`, `id`, `values` |
| `db_delete` | **yes** | `model`, `id` |

Writes validate `values` against the model's fields (unknown fields and `owner_id`
are rejected), emit a `db.*` event, and append an audit entry. Reads are
owner-scoped; `limit` is capped at 100.

```python
agent.database({"note": Note})
```

### Scheduler

Manage durable schedules for allow-listed tasks.

| Tool | Approval | Args |
| --- | --- | --- |
| `schedule_task` | **yes** | `name`, `task`, `cron=None`, `at=None`, `args={}` |
| `list_schedules` | no | — |
| `get_schedule` | no | `name` |
| `cancel_schedule` | no | `name`, `delete=False` |
| `run_schedule_now` | **yes** | `name` |

Cron expressions are validated; pass exactly one of `cron` or `at`. Tasks are
restricted to the allow-list.

```python
agent.scheduler(["sync_notes"])
```

### Queue

Enqueue background work and inspect the queue. Both enqueues honour
`QUEUE_ENABLED` (inline when the queue is off, pushed to a worker otherwise).

| Tool | Approval | Args |
| --- | --- | --- |
| `enqueue_task` | **yes** | `task`, `args={}`, `delay=0`, `queue=None` |
| `enqueue_job` | **yes** | `job`, `kwargs={}`, `delay=0`, `queue=None` |
| `queue_status` | no | `queue=None` |
| `list_failed_jobs` | no | `limit=20` |
| `retry_job` | no | `id` |

`enqueue_task` runs an allow-listed scheduler task as a `RunRegisteredTask` job;
`enqueue_job` dispatches an allow-listed `Job` class. Tasks share the scheduler
allow-list; jobs use their own.

```python
agent.queue({"sync": SyncNotes}).scheduler(["sync_notes"])
```

### Notifications

| Tool | Approval | Args |
| --- | --- | --- |
| `notify` | **yes** | `text`, `channels=["conversation"]` |
| `notify_me` | no | `text` |

`conversation` writes into the current conversation; other channels go through the
configured gateway senders.

### History

Owner-scoped reads over past conversations.

| Tool | Approval | Args |
| --- | --- | --- |
| `list_conversations` | no | `limit=20` |
| `search_history` | no | `query`, `limit=10` |
| `read_conversation` | no | `id`, `limit=20` |

### Usage & audit

Read-only operational insight.

| Tool | Approval | Args |
| --- | --- | --- |
| `usage_summary` | no | `window="all"` |
| `audit_trail` | no | `limit=20` |
| `verify_audit` | no | — |

### Knowledge admin

Index, replace, and forget RAG documents. Writes require approval; `index_document`
is additive.

| Tool | Approval | Args |
| --- | --- | --- |
| `index_document` | no | `text`, `source` |
| `replace_document` | **yes** | `source`, `text` |
| `forget_document` | **yes** | `source` |
| `list_documents` | no | — |

```python
agent.knowledge_admin()
```

### Skill authoring

Write valid `SKILL.md` files into the skills directory. Both tools require
approval and re-discover the registry after writing.

| Tool | Approval | Args |
| --- | --- | --- |
| `save_skill` | **yes** | `name`, `description`, `body`, `allowed_tools=[]` |
| `update_skill` | **yes** | `name`, `body` |

```python
agent.skill_authoring()
```

## The safety model

- **Allow-lists** — the app names the reachable models/tasks/jobs; everything else
  returns an error.
- **Approval** — mutating tools defer to your approver (see
  [Human-in-the-Loop](/guide/hitl)). Registration-based: each write is registered
  with `requires_approval=True`.
- **Owner scoping** — repositories filter by `owner_id`; no cross-owner reads.
- **Audit** — writes append a hash-chained audit entry and emit events
  (`db.*`, `schedule.*`, `queue.*`, `notify.*`, `knowledge.*`, `skill.*`).
- **No raw SQL** — the database toolkit works through typed repositories only.

::: tip Seeing what is on
`agentkit inspect` and `GET /api/info` report the enabled toolkits, their flags,
and the allow-listed models/tasks/jobs. See [The Full Stack](/guide/fullstack).
:::

Continue to [Self-Learning →](/guide/self-learning)
