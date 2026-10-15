# Self-Learning

## Introduction

Agentkit agents can **learn from their own experience**. A closed
**reflect → learn → apply** loop distils durable lessons ("when X, do Y"),
preferences, and facts from conversation history, stores them, and injects them
back into future turns so behaviour changes over time.

Learning is opt-out (`LEARNING_ENABLED=true` by default), transparent (CLI + the
stack view report its state), and bounded (caps, dedupe, decay, redaction).

## The loop

```
   turns ──► reflect ──► learn ──► apply ──► future turns
             (extract)   (store)   (digest + skills)
```

- **Reflect** — `reflect(repos)` reads a window of a conversation and extracts
  lessons, preferences, and facts with a model (JSON-only) or an offline
  heuristic. It is **idempotent** per conversation + window via a `learning_runs`
  record, so re-running is cheap.
- **Learn** — lessons are stored as `procedural` memories (deduped via
  `near_duplicates`/`merge`), preferences merge into the owner profile, and facts
  become memories. Secrets and PII are redacted before storage.
- **Apply** — `lessons_digest(repos)` is injected into the instructions by
  `.learning()`/`.full()`, and recurring lessons can be distilled into a
  `SKILL.md`.

## Enabling learning

```python
from agentkit import Agent

agent = (
    Agent.make("assistant")
    .instructions("Be helpful.")
    .learning()               # reflect -> learn -> apply
    .output(str)
    .build()
)
```

`.full()` attaches learning automatically when `LEARNING_ENABLED=true`; an explicit
`.learning()` opts in regardless of the flag. `.learning(False)` disables it.

## Tools

`.learning()` adds four tools:

| Tool | Approval | Args | Purpose |
| --- | --- | --- | --- |
| `learn` | no | `insight`, `kind="lesson"` | record a lesson/preference/fact now |
| `reflect` | no | — | review recent turns and distil lessons |
| `list_lessons` | no | `limit=20` | show what the agent has learned |
| `forget_lesson` | no | `id` | drop a bad lesson |

`learn` redacts PII/secrets and stores the insight as a memory
(`lesson`/`procedural` → `procedural`). Use it right after finishing a task:

```python
# the model calls this itself:
learn("when the user mentions a deadline, add a calendar reminder")
```

## The digest

Learned lessons are ranked by importance and access count and injected into the
instructions as a compact block, so the agent applies them without calling a tool:

```python
from agentkit import lessons_digest

async with app.repositories() as repos:
    print(await lessons_digest(repos))
```

`lessons_digest` returns `None` when there are no lessons yet.

## Signals

A `LearningSignals` buffer subscribes to the event dispatcher (`turn.end`,
`agent.error`, …) and keeps a **bounded, redacted** ring buffer of recent signals
that reflection can draw on:

```python
from agentkit import LearningSignals

signals = LearningSignals(capacity=200)
signals.subscribe(app.events)          # feeds from turn.end / agent.error
signals.recent(limit=20)
```

## Storage & guardrails

- **Storage** — lessons are `Memory(kind="procedural")` with
  `source_conversation_id` and an `importance` derived from the evidence;
  preferences merge into `OwnerProfile.preferences`.
- **Redaction** — PII (`redact_pii`) and secrets (`redact`) are stripped before
  anything is stored; credentials are never learned.
- **Caps** — `LEARNING_WINDOW` bounds the turns reviewed, and
  `LEARNING_MAX_LESSONS` caps how many lessons a single reflection writes.
- **Dedupe** — near-identical lessons are merged after distillation (distillation
  runs first so a recurring lesson is still counted).
- **Flag** — `LEARNING_ENABLED=false` disables the tools and the durable task.

| Setting | Default | Purpose |
| --- | --- | --- |
| `LEARNING_ENABLED` | `true` | master switch |
| `LEARNING_REFLECT_CRON` | `0 4 * * *` | durable reflection schedule |
| `LEARNING_WINDOW` | `20` | turns reviewed per reflection |
| `LEARNING_MAX_LESSONS` | `50` | lessons written per reflection |
| `LEARNING_SKILL_THRESHOLD` | `3` | recurrences before a skill candidate |
| `LEARNING_AUTO_SKILLS` | `false` | write `SKILL.md` automatically |

## Skill distillation

When the same lesson recurs at least `LEARNING_SKILL_THRESHOLD` times, reflection
reports it as a **skill candidate**. With `LEARNING_AUTO_SKILLS=true` it also
writes a `SKILL.md` into the skills directory (reusing the skill-authoring
toolkit), turning a repeated correction into a durable capability:

```python
summary = await reflect(repos, auto_skills=True, skill_threshold=2)
summary["skill_candidates"]   # [{"name": …, "count": …, "lessons": [...]}]
summary["skills"]             # ["…"] once written
```

See [Skills](/guide/skills) for the `SKILL.md` format.

## CLI

```bash
agentkit learning:reflect --dry-run          # report without changing anything
agentkit learning:reflect --conversation cli:1 --window 20
agentkit learning:lessons --limit 20         # list what was learned
agentkit learning:forget 12                  # delete a lesson by id
```

## Durable scheduling

`FullStackProvider.boot` registers the `learning:reflect` scheduler task and
schedules it daily (`LEARNING_REFLECT_CRON`, or the `learning` config section's
`reflect_cron`). Reflection thus runs without a user present:

```python
from agentkit import App, FullStackProvider

app = App(name="assistant").providers([FullStackProvider])
app.boot()   # registers + schedules learning:reflect (and memory:consolidate)
```

Registering the task directly is idempotent:

```python
from agentkit import register_reflect_task
from agentkit.scheduler import TASKS

register_reflect_task()
assert "learning:reflect" in TASKS
```

## Review inbox

Set `LEARNING_REQUIRE_REVIEW=true` to hold new lessons as `proposed` until you
approve them — they are never applied (or distilled into skills) while pending.
Memories carry a `status` (`active` | `proposed` | `rejected`); only `active`
rows show up in listings, search, the digest, and distillation.

```bash
agentkit learning:lessons --status proposed
agentkit learning:review approve 12
agentkit learning:review reject 13
```

The web UI exposes the same inbox at `GET /api/lessons?status=proposed` with
`POST /api/lessons/{id}/approve` and `.../reject`. Programmatically:
`approve_lesson(repos, id)` / `reject_lesson(repos, id)` / `proposed_lessons(repos)`.

## Eval-driven learning

Turn real conversations into regression cases and gate on them:

```python
from agentkit.evals import capture_turns, load_captured

await capture_turns(repos, conversation_id="cli:default")   # prompt -> reply pairs
suite = await load_captured(repos)
report = await suite.run(app)
```

```bash
agentkit eval:capture --conversation cli:default
agentkit eval:gate --bootstrap app:app     # exits non-zero on regression
```

Captured cases live in the `evals_capture` table; `LEARNING_EVAL_GATE` reports
intent to gate post-reflection on them (surfaced in the stack view).

::: warning Reflection is best-effort
Reflection never blocks a turn and never raises into the scheduler — a failed or
empty reflection is a no-op. Keep `LEARNING_AUTO_SKILLS` off until you trust the
quality of the distilled lessons.
:::

Continue to [The Full Stack →](/guide/fullstack)
