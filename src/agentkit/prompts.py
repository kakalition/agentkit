"""A file-backed prompt registry with light versioning.

Prompts live under ``prompts/<name>.md`` with optional YAML front matter::

    ---
    version: 3
    description: Greets a new user
    ---
    You are {persona}. Greet {name} warmly.

The registry discovers them, tracks versions (the highest version wins), and
renders ``{variables}``::

    from agentkit.prompts import PromptRegistry

    prompts = PromptRegistry.from_settings().discover()
    text = prompts.render("greeting", persona="Nudge", name="Ada")

Wire one into an agent with ``Agent.make(...).prompt(prompts, "greeting")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentkit.skills import parse_front_matter
from agentkit.support.kinds import DriverKind, PromptsDriver
from agentkit.support.manager import Manager

__all__ = [
    "DEFAULT_PROMPT_DIR",
    "Prompt",
    "PromptManager",
    "PromptRegistry",
    "load_prompt_file",
]

DEFAULT_PROMPT_DIR = "prompts"


@dataclass
class Prompt:
    name: str
    body: str
    version: int = 1
    description: str = ""
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, **variables: Any) -> str:
        if not variables:
            return self.body
        try:
            return self.body.format(**variables)
        except (KeyError, IndexError, ValueError):
            return self.body


def load_prompt_file(path: Path) -> Prompt:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    version_raw = meta.get("version", 1)
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        version = 1
    return Prompt(
        name=str(meta.get("name") or path.stem),
        body=body,
        version=version,
        description=str(meta.get("description", "")),
        path=path,
        metadata=dict(meta),
    )


class PromptRegistry:
    """Discovers ``prompts/*.md``, keeping the highest version of each name."""

    def __init__(self, roots: list[Path] | None = None) -> None:
        self.roots = [Path(root).expanduser() for root in (roots or [])]
        self._prompts: dict[str, Prompt] = {}

    @classmethod
    def from_settings(cls, settings: Any = None) -> PromptRegistry:
        if settings is None:
            from agentkit.config import get_settings

            settings = get_settings()
        roots: list[Path] = []
        configured = getattr(settings, "prompts_dir", None)
        if configured:
            roots.append(Path(configured).expanduser())
        else:
            roots.append(Path.cwd() / DEFAULT_PROMPT_DIR)
            home = getattr(settings, "home", None)
            if home is not None:
                roots.append(Path(home) / DEFAULT_PROMPT_DIR)
        return cls(roots)

    def discover(self, *, reload: bool = False) -> PromptRegistry:
        if reload:
            self._prompts.clear()
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.md")):
                try:
                    self.register(load_prompt_file(path))
                except Exception:  # pragma: no cover - skip malformed prompts
                    continue
        return self

    def register(self, prompt: Prompt) -> Prompt:
        existing = self._prompts.get(prompt.name)
        if existing is None or prompt.version >= existing.version:
            self._prompts[prompt.name] = prompt
        return prompt

    def get(self, name: str) -> Prompt | None:
        return self._prompts.get(name)

    def names(self) -> list[str]:
        return sorted(self._prompts)

    def render(self, prompt_name: str, **variables: Any) -> str:
        prompt = self.get(prompt_name)
        if prompt is None:
            raise KeyError(f"no prompt named {prompt_name!r}; have {self.names()}")
        return prompt.render(**variables)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._prompts


class PromptManager(Manager):
    """Resolves the configured prompt store (``prompts_driver``, default ``file``).

    Drivers are :class:`PromptRegistry` instances; ``file`` discovers
    ``prompts/*.md`` under the configured roots, ``memory`` starts empty.
    """

    kind = DriverKind.PROMPTS
    default_driver = PromptsDriver.FILE

    def create_file_driver(self, app: Any) -> PromptRegistry:
        settings = getattr(app, "settings", None)
        return PromptRegistry.from_settings(settings).discover()

    def create_memory_driver(self, app: Any) -> PromptRegistry:
        return PromptRegistry([])
