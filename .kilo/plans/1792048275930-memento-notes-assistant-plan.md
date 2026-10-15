# Memento — Personal Knowledge/Notes Assistant (agentkit use-case project)

## Goal

Build **`memento`**, a standalone, runnable use-case project that demonstrates
agentkit end to end as a **personal knowledge/notes assistant**: capture notes,
tag and organize them, semantically recall them, set reminders, produce a weekly
digest, and let the agent learn the owner's note-taking preferences over time —
all owner-scoped, approval-gated for writes, audited, and operable from the
built-in web UI.

The project is a normal agentkit full-stack app (not a framework change). It
lives **outside the agentkit repo** so it exercises agentkit the way a real user
would.

## Context (what agentkit already provides)

- `App` container + service `Provider`s + `Agent.make(...)` fluent builder + an
  Artisan-style CLI (`new`, `serve`, `tinker`, `inspect`, `schedule:*`,
  `learning:*`, `eval`).
- Durable SQLite (`~/.agentkit/<name>/`): conversations, memory, knowledge,
  schedules, usage, hash-chained audit.
- **Native toolkits** (agent-callable, allow-listed, approval-gated writes):
  `database` (`db_*`), `scheduler` (`schedule_*`), `queue` (`enqueue_*`),
  `notifications` (`notify`/`notify_me`), `history`, `usage`, `knowledge_admin`,
  `skill_authoring`.
- **Self-learning** (`learning()`): reflect → learn → apply; durable daily
  `learning:reflect`; lessons injected via `lessons_digest`.
- `FullStackProvider` wires config sections, `memory:consolidate`, `learning:reflect`,
  and any configured channels (idle unless a token is set).
- The `agentkit new` scaffold already ships a working **Note** model, repository,
  service, tools, job, notification, event/listener, policy, skill, and evals —
  the ideal base to extend into this use case.

## Decisions (locked)

| Decision | Value |
| --- | --- |
| Project name / agent name | `memento` |
| Location | `/Users/kharisma/Workspaces/memento` (sibling of the agentkit checkout) |
| agentkit dependency | `uv` editable path source → `../agentkit` |
| Scope | Full-stack notes assistant (DB tools, scheduler, queue, notifications, history, usage, knowledge admin, skill authoring, learning, web UI, evals) |
| Base | `agentkit new memento` full-stack scaffold, then extended |
| Model | framework default `openai:gpt-4o-mini`; tests run offline (no network) |
| Channels | none enabled by default (web UI + `tinker`); gateways stay idle |
| Storage | default `~/.agentkit/memento` |

## Deliverable layout

```
/Users/kharisma/Workspaces/memento/
  pyproject.toml                 # uv, editable agentkit path source
  .env.example                   # OPENAI_API_KEY, MODEL_NAME, LEARNING_ENABLED...
  bootstrap.py                   # App(name="memento", repos_factory=AppRepositories) + providers
  SOUL.md                        # memento persona
  app/
    config.py                    # Settings + AppSection
    Agents/assistant.py          # build_assistant() — the agent builder
    Providers/AppServiceProvider.py
    Providers/EventServiceProvider.py
    Console/Kernel.py            # schedule: sync-notes, digest
    Console/Commands/…           # keep scaffold's note:pin
    Models/Note.py               # extended Note table
    Repositories/                # AppRepositories + NoteRepository
    Services/NoteService.py      # capture/search/tag/archive + KB indexing hook
    Tools/notes.py               # agent tools
    Jobs/                        # sync_notes, digest, remind tasks
    Notifications/               # NoteSaved, NotesDigest, Reminder
    Events/ + Listeners/         # note.saved payload + IndexNoteOnSave + LogNoteSaved
    Middleware/Timing.py
    Policies/MementoPolicy.py
    Rules/NonEmpty.py
    Repositories/…               # (as generated)
  config/learning.py, config/memory.py, config/channels.py
  skills/note-formats/SKILL.md   # capture formats (meeting/idea/task)
  skills/daily-review/SKILL.md   # weekly review how-to
  prompts/system.md
  evals/notes.yaml               # capture + recall + tag cases
  tests/                         # repository/service + indexing + schedule + approval + build
  database/README.md, storage/, .gitignore, README.md
```

## Domain design

**`Note` (SQLModel, `table=True`, table `notes`)**
`id`, `owner_id` (indexed), `title`, `body`, `tags` (normalized lowercase
comma-separated string), `source` (`"chat" | "cli" | "web"`), `pinned: bool`,
`archived: bool`, `created_at`, `updated_at`.

No extra tables: **reminders** reuse durable one-off schedules; **tags** are
derived from the `tags` string (keeps the demo small and uses native toolkits as
designed). If a normalized tag table is later wanted, add `Tag` + a join and add
both to the agent's `database(...)` allow-list.

**Knowledge / recall**
One `KnowledgeBase` instance is built in `AppServiceProvider` and shared into the
agent via `.knowledge(kb)`. `IndexNoteOnSave` (listener on `note.saved`) indexes
each note as `source=f"note:{id}"`; `sync_notes` re-indexes on a schedule to
repair drift. Semantic search uses `search_knowledge`; `search_notes` adds a
lexical fallback over `title`/`body`/`tags`.

## Ordered tasks

1. **Scaffold the project.**
   `uv run --project /Users/kharisma/Workspaces/agentkit agentkit new memento --path /Users/kharisma/Workspaces --git`
   (full-stack, default). Confirm `tests/test_smoke.py` passes inside the new
   project after step 2.
2. **Wire the agentkit dependency.** Edit `pyproject.toml`:
   `dependencies = ["agentkit"]` + `[tool.uv.sources]` →
   `agentkit = { path = "../agentkit", editable = true }`; add the `memory` and
   `dev` extras. Run `uv sync`.
3. **Extend the `Note` model** (add `title`, `body`, `tags`, `source`, `archived`,
   timestamps; keep `pinned`) and `NoteRepository` helpers (`by_tag`, `recent`,
   `search_lexical`).
4. **Extend `NoteService`** with `capture`, `search`, `tag`, `archive`, plus the
   knowledge-index write (append to the shared `KnowledgeBase`).
5. **Add the agent tools** in `app/Tools/notes.py`:
   `capture_note(title, body, tags="")` (emits `note.saved`),
   `search_notes(query, limit=5)`, `list_notes(tag=None, limit=20)`,
   `get_note(id)`, `tag_note(id, tags)`, `archive_note(id)`,
   `set_reminder(message, at)` (calls `scheduler.schedule_once("remind", at,
   "remind", args={...})`), keep `current_time`. Register `archive_note` with
   `requires_approval=True`.
6. **Add durable tasks** in `app/Jobs/`: `sync_notes` (re-index notes),
   `digest` (weekly summary notification: notes captured, top tags, stale notes),
   `remind` (notify the reminder message). Each exposes `run()` + `register()`
   via `scheduler.task(name)`, registered in `AppServiceProvider.boot`.
7. **Build the agent** in `app/Agents/assistant.py`:
   `.persona() .instructions(...)`
   `.tool(capture_note, search_notes, list_notes, get_note, tag_note, archive_note, set_reminder, current_time)`
   `.knowledge(kb)` `.database({"note": Note})`
   `.scheduler(["sync_notes", "digest", "remind"])` `.queue({"sync": SyncNotes})`
   `.notifications() .history() .usage() .knowledge_admin() .skill_authoring()`
   `.learning() .full() .policy(memento_policy()) .output(str)`.
   Record allow-lists on the app too: `app.models({"note": Note})`,
   `app.agent_tasks([...])`, `app.agent_jobs({...})` in `AppServiceProvider`.
8. **Console kernel:** schedule `sync-notes` every 15 minutes and `digest`
   weekly (Mon 08:00). Do **not** re-schedule `memory:consolidate`/`learning:reflect`
   — `FullStackProvider` already registers those (avoids duplicates).
9. **Notifications + events + listeners:** `NoteSaved`, `NotesDigest`,
   `Reminder` notifications; `IndexNoteOnSave` and `LogNoteSaved` listeners;
   `EventServiceProvider` registers them.
10. **Skills + prompts + persona:** write `skills/note-formats/SKILL.md`,
    `skills/daily-review/SKILL.md`, `prompts/system.md`, and a memento `SOUL.md`.
11. **Config + env:** keep `config/{learning,memory,channels}.py`; set `.env.example`
    (`OPENAI_API_KEY=`, `MODEL_NAME=openai:gpt-4o-mini`, `LEARNING_ENABLED=true`,
    commented channel tokens). `conftest.py` already forces the offline `hash`
    embedder, `OBSERVABILITY=off`, `WEBUI_ENABLED=false`, temp `AGENT_HOME`.
12. **Tests** (`tests/`): service/repository CRUD; note→KB indexing and recall
    (offline `hash` embedder); schedule registration (`sync-notes`, `digest`);
    allow-list enforcement (non-allow-listed model errors); approval flags
    (`archive_note`/`db_delete` require approval); built agent exposes expected
    tools/toolkits. Use PydanticAI `TestModel`/`FunctionModel` for any
    turn-level test — no network.
13. **Evals:** `evals/notes.yaml` — capture creates a note, recall finds a prior
    note, tagging is applied, persona holds.
14. **README:** what memento is, the use case, quickstart, the primitives it
    demonstrates, and how to extend (add a tag table, enable Telegram).
15. **Validation** (below) and fix anything that fails.

## Risks / failure modes

- **No `OPENAI_API_KEY`.** Live turns fail; keep unit tests model-free and use
  `TestModel` for turn tests so CI stays green without a key.
- **Embeddings.** Offline `hash` embedder for tests; real semantic recall needs
  the `agentkit[memory]` extra (document it).
- **Approvals default-deny.** Write tools (incl. `archive_note`, `db_*`) defer to
  an approver; the demo must wire an approver (web UI approval queue) or the user
  runs the CLI/tinker with an approval handler. Document this explicitly.
- **Duplicate schedules.** `FullStackProvider` schedules `memory:consolidate` and
  `learning:reflect`; the Kernel must not duplicate them.
- **KB drift.** Notes edited/archived/deleted must not leave stale KB entries;
  `sync_notes` re-indexes and `archive_note` removes/marks the KB doc.
- **Cross-thread SQLite writes.** Notification/event listeners must write through
  the current repositories session, not a separate sync writer mid-loop.
- **Naming collisions.** Tool names must not clash with toolkit tools
  (`db_*`, `schedule_*`, `notify*`); verify via `agentkit inspect`.
- **Out-of-workspace writes.** The project lives outside the agentkit repo; the
  implementation agent needs write access to `/Users/kharisma/Workspaces/memento`.

## Validation

```bash
cd /Users/kharisma/Workspaces/memento
uv sync
uv run pytest -q                      # hermetic tests, offline, no network
uv run ruff check .
cp .env.example .env && $EDITOR .env  # set OPENAI_API_KEY
uv run agentkit inspect               # tools, toolkits, allow-lists, schedules
uv run agentkit tinker                # manual: capture a note, then recall it
uv run agentkit serve                 # web UI: notes, schedules, audit, lessons
uv run agentkit eval evals/notes.yaml
uv run agentkit learning:reflect --dry-run
```

Done when: tests + ruff pass; `agentkit inspect` shows the expected tools and
toolkits with the note allow-list; capturing then recalling a note works through
`tinker`; the web UI lists conversations, schedules, audit, and lessons; and the
eval suite passes.

## Out of scope

- No changes to the agentkit framework/repo (no new primitives, no doc edits
  there).
- No published release; the project pins the local editable checkout.
- No Telegram/Slack/Email/Discord activation (capability present, tokens unset).
- No Postgres/multi-tenant/auth setup (single local owner).

## Open questions

- Should `memento` also expose a small **HTTP ingest** endpoint for browser
  capture (agentkit webhooks) beyond chat/tinker? Default: no, all capture goes
  through chat/tinker/web UI until asked.
