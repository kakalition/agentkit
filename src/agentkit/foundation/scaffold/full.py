"""The full-stack project overlay (``agentkit new`` default)."""

from __future__ import annotations

from pathlib import Path

from agentkit.foundation.scaffold.minimal import MINIMAL_FILES, package_name, pascal

__all__ = ["FULL_FILES", "scaffold_project"]

_FULL_STACK_README = """
## The full stack

The default project ships the **whole agent stack**, wired through
`App(...).fullstack()` (`FullStackProvider`). Every layer is opt-out:

| Layer | On when | Opt out |
| --- | --- | --- |
| Model providers | `MODEL_NAME=provider:model` | — |
| Memory (typed facts + profile) | `MEMORY_ENABLED=true` | `MEMORY_ENABLED=false` |
| Memory consolidation | memory enabled | `AGENTKIT_MEMORY_CONSOLIDATION_CRON` / disable memory |
| Skills | `SKILLS_ENABLED=true` | `SKILLS_ENABLED=false` |
| HITL approvals | `APPROVALS_ENABLED=true` | `APPROVALS_ENABLED=false` |
| Channels | token/env present | leave the channel's token unset |
| Sub-agents / mailbox | `SUBAGENTS_ENABLED=true` | `SUBAGENTS_ENABLED=false` |
| Queue | `QUEUE_ENABLED=true` | `QUEUE_ENABLED=false` |

Unconfigured layers stay idle (a debug log, never an error). See
`docs/guide/fullstack.md` in the agentkit repository for details.
"""

_FULL_STACK_ENV = """
# -- Providers (set the key for the provider in MODEL_NAME) ------------------
# MODEL_NAME=openai:gpt-4o-mini
# ANTHROPIC_API_KEY=
# GOOGLE_API_KEY=
# GROQ_API_KEY=
# MISTRAL_API_KEY=
# OLLAMA_BASE_URL=http://localhost:11434/v1
# OPENAI_BASE_URL=            # for openai-compatible endpoints
# -- Channels (each activates only when its token/env is present) ------------
# TELEGRAM_BOT_TOKEN=
# SLACK_BOT_TOKEN=
# SLACK_APP_TOKEN=
# DISCORD_BOT_TOKEN=
# EMAIL_IMAP_HOST=
# EMAIL_SMTP_HOST=
# EMAIL_FROM=
# -- Multi-agent ------------------------------------------------------------
SUBAGENTS_ENABLED=false
"""


def _full_overlay() -> dict[str, str]:
    """Extra files (and overrides) that make the scaffold the full-stack project."""
    return {
        "bootstrap.py": '''"""The application entry point.

``agentkit serve`` boots ``bootstrap:app``, so this is the single place your app is
assembled: settings, the repository container, and the service providers.
``FullStackProvider`` wires the whole stack (config sections, the daily
``memory:consolidate`` schedule, and any configured channels).
"""

from __future__ import annotations

from agentkit import App, FullStackProvider

from app.config import Settings
from app.Providers.AppServiceProvider import AppServiceProvider
from app.Providers.EventServiceProvider import EventServiceProvider
from app.Repositories import AppRepositories

app = App(name="{{project}}", settings=Settings, repos_factory=AppRepositories)
app.providers([EventServiceProvider, AppServiceProvider, FullStackProvider])
''',
        "app/Agents/assistant.py": '''"""The agent, built declaratively with ``Agent.make(...).full()``."""

from __future__ import annotations

from agentkit import Agent

from app.Policies.AssistantPolicy import assistant_policy
from app.Tools.notes import add_note, current_time, list_notes

INSTRUCTIONS = (
    "You are {{project}}, a concise and helpful assistant. Use your tools when "
    "they help, remember durable facts about the owner, and load a skill when it "
    "is relevant."
)


def build_assistant() -> Agent:
    return (
        Agent.make("{{project}}")
        .instructions(INSTRUCTIONS)
        .tool(current_time)
        .tool(add_note)
        .tool(list_notes)
        # The whole agent stack: persona + memory + skills + HITL + safety
        # (each layer skipped when its settings flag disables it).
        .full()
        .policy(assistant_policy())
        .output(str)
    )
''',
        "app/Console/Kernel.py": '''"""The console kernel: the schedule and the command list.

``app.schedule(...)`` is the fluent scheduler (Laravel's ``$schedule``).
"""

from __future__ import annotations

from typing import Any

from app.Console.Commands.PinNote import PinNoteCommand


class Kernel:
    def schedule(self, app: Any) -> None:
        # A durable heartbeat (survives restarts; see `agentkit schedule:list`).
        app.schedule("sync_notes").name("sync-notes").every_fifteen_minutes().without_overlapping().description("Sync notes into the knowledge base.")
        # Daily memory consolidation (dedupe / summarize / prune).
        app.schedule("memory:consolidate").name("memory-consolidate").daily_at("03:00").description("Consolidate durable memories.")

    def commands(self) -> list[Any]:
        return [PinNoteCommand()]
''',
        "app/Channels/__init__.py": '''"""Channels — transports that deliver turns to and from the agent."""
''',
        "app/Channels/Example.py": '''"""An example channel factory. Register it with ``app.channel("example", ExampleChannel)``.

A channel returns a ``Service`` (a blocking ``run()``); the built-in Telegram /
Slack / Email / Discord gateways are registered automatically by
``FullStackProvider`` when their tokens are configured.
"""

from __future__ import annotations

from typing import Any

from agentkit.supervise import Service


def ExampleChannel(app: Any) -> Service:
    def run() -> None:
        # Long-poll or listen here; call ``await app.answer(conversation_id, text)``
        # for each inbound message, then deliver the result back to the transport.
        app.settings  # noqa: B018 - placeholder

    return Service(name="example", run=run)
''',
        "config/memory.py": """\
# Overrides for the "memory" config section (defaults < this file < environment).
config = {"enabled": True, "consolidation_cron": "0 3 * * *"}
""",
        "config/channels.py": """\
# Overrides for the "channels" config section.
config = {"enabled": True}
""",
        "README.md": MINIMAL_FILES["README.md"] + _FULL_STACK_README,
        ".env.example": MINIMAL_FILES[".env.example"] + _FULL_STACK_ENV,
    }


FULL_FILES: dict[str, str] = {**MINIMAL_FILES, **_full_overlay()}


def scaffold_project(
    name: str, directory: str | Path = ".", *, force: bool = False, full: bool = True
) -> Path:
    """Write the skeleton for ``name`` into ``directory/name`` and return the path.

    ``full=True`` (the default) writes the full-stack project; ``full=False`` writes
    the minimal skeleton. Refuses to write into a non-empty target unless
    ``force=True``.
    """
    package = package_name(name)
    target = Path(directory).expanduser() / name
    if target.exists() and any(target.iterdir()) and not force:
        raise FileExistsError(f"{target} already exists and is not empty (pass force=True)")

    files = FULL_FILES if full else MINIMAL_FILES
    replacements = {
        "{{project}}": name,
        "{{package}}": "app",  # Laravel-style flat `app/` package
        "{{Project}}": pascal(name),
        "{{PREFIX}}": package.upper(),
    }
    for relative, template in files.items():
        content = template
        for key, value in replacements.items():
            content = content.replace(key, value)
        destination = target / relative.replace("{{package}}", "app")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return target
