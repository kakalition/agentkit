"""SOUL.md — the agent's persona/identity, loaded into its instructions.

``SOUL.md`` is a plain Markdown file describing who the agent is and how it
behaves. agentkit composes it with the application's routing/tool instructions
so the persona is data (editable) rather than hard-coded.
"""

from __future__ import annotations

from pathlib import Path

from agentkit.config import AgentSettings, get_settings

SOUL_FILENAME = "SOUL.md"

DEFAULT_SOUL = """\
# Soul

I am a personal assistant. I solve by doing, not by describing what I would do.
I keep replies short unless depth is asked for, say what I know and flag what I
don't, and never fake confidence. I treat the user's time as scarce and their
trust as the most valuable thing.
"""


def soul_path(settings: AgentSettings | None = None) -> Path:
    settings = settings or get_settings()
    soul_file = getattr(settings, "soul_file", None)
    if soul_file:
        return Path(soul_file).expanduser()
    return settings.agent_home / SOUL_FILENAME


def load_soul(settings: AgentSettings | None = None) -> str:
    """Return the agent's SOUL text (falls back to the built-in default)."""
    path = soul_path(settings)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_SOUL
    return text or DEFAULT_SOUL


def ensure_soul(settings: AgentSettings | None = None, *, overwrite: bool = False) -> Path:
    """Create a SOUL.md from the default template if it does not exist."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    path = soul_path(settings)
    if overwrite or not path.exists():
        path.write_text(DEFAULT_SOUL, encoding="utf-8")
    return path


def compose_instructions(soul: str, instructions: str | None = None) -> str:
    """Combine the persona with the application's instructions."""
    parts = [soul.strip()]
    if instructions:
        parts.append(instructions.strip())
    return "\n\n".join(parts)
