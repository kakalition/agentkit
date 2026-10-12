"""Skills: discoverable folders of instructions an agent can load on demand.

A *skill* is a directory containing a ``SKILL.md`` with optional YAML
front matter::

    skills/
      pdf-tools/
        SKILL.md
        references/style.md
        scripts/extract.py

    ---
    name: pdf-tools
    description: Extract text and tables from PDF files.
    allowed-tools: [read_file, run_script]
    ---
    # PDF tools
    Use `read_skill_file` to load reference docs, then ...

The registry scans one or more roots (project ``./skills``, the agent home's
``skills/``, or an explicit ``settings.skills_dir``), parsing each ``SKILL.md``.
The agent gets a compact **index** (name + description) in its instructions and
three tools to use skills: ``list_skills``, ``load_skill`` (full instructions on
demand) and ``read_skill_file`` (bundled reference files, path-traversal safe).

This is progressive disclosure — the model sees *what* skills exist cheaply and
pulls the *how* only when a skill is relevant.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("agentkit.skills")

SKILL_FILENAME = "SKILL.md"
DEFAULT_SKILL_DIR = "skills"
_FRONT_MATTER_FENCE = "---"


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_scalar(value: str) -> Any:
    value = _strip_quotes(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(part) for part in inner.split(",") if part.strip()]
    return value


def _parse_front_matter_minimal(text: str) -> dict[str, Any]:
    """Parse the flat ``key: value`` / block-list subset skills actually use."""
    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.lstrip().startswith("- ") and current_list:
            data.setdefault(current_list, []).append(_strip_quotes(raw.lstrip()[2:]))
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            current_list = None
            if value:
                data[key] = _parse_scalar(value)
            else:
                data[key] = []
                current_list = key
    return data


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a ``SKILL.md`` into (front matter, body)."""
    stripped = text.lstrip("\ufeff")
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return {}, stripped.strip()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONT_MATTER_FENCE:
            end = index
            break
    if end is None:
        return {}, stripped.strip()
    raw_meta = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).strip()
    try:  # use PyYAML when present for full YAML; fall back to the subset parser
        import yaml

        parsed = yaml.safe_load(raw_meta)
        meta = parsed if isinstance(parsed, dict) else {}
    except Exception:
        meta = _parse_front_matter_minimal(raw_meta)
    return meta, body


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    """One discovered skill."""

    name: str
    path: Path
    description: str = ""
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed_tools(self) -> list[str]:
        value = self.metadata.get("allowed-tools") or self.metadata.get("allowed_tools") or []
        if isinstance(value, str):
            return [value]
        return list(value)

    def files(self) -> list[str]:
        """Bundled support files (relative, posix), excluding ``SKILL.md``."""
        if not self.path.is_dir():
            return []
        return sorted(
            p.relative_to(self.path).as_posix()
            for p in self.path.rglob("*")
            if p.is_file() and p.name != SKILL_FILENAME
        )

    def read(self, relative: str) -> str:
        """Read a bundled file, refusing to escape the skill directory."""
        target = (self.path / relative).resolve()
        root = self.path.resolve()
        if not (target == root or str(target).startswith(str(root) + "/")):
            raise ValueError(f"path {relative!r} escapes skill {self.name!r}")
        return target.read_text(encoding="utf-8")

    def render(self) -> str:
        """The full skill text handed to the model when it is loaded."""
        parts = [f"# Skill: {self.name}"]
        if self.description:
            parts.append(self.description)
        if self.body:
            parts.append(self.body)
        files = self.files()
        if files:
            parts.append(
                "Bundled files (read with `read_skill_file`): " + ", ".join(f"`{f}`" for f in files)
            )
        return "\n\n".join(parts)


def load_skill_file(skill_md: Path) -> Skill:
    """Parse one ``SKILL.md`` into a :class:`Skill`."""
    text = skill_md.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    name = str(meta.get("name") or skill_md.parent.name).strip()
    description = str(meta.get("description", "")).strip()
    return Skill(
        name=name,
        path=skill_md.parent,
        description=description,
        body=body,
        metadata=dict(meta),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SkillRegistry:
    """Discovers and serves skills from one or more roots."""

    def __init__(self, roots: list[Path] | None = None, *, skills: list[Skill] | None = None) -> None:
        self.roots: list[Path] = [Path(root).expanduser() for root in (roots or [])]
        self._skills: dict[str, Skill] = {}
        for skill in skills or []:
            self.register(skill)

    # -- construction ---------------------------------------------------
    @classmethod
    def from_paths(cls, paths: Sequence[str | Path] | None = None) -> SkillRegistry:
        return cls([Path(p) for p in paths] if paths else [])

    @classmethod
    def from_settings(cls, settings: Any = None) -> SkillRegistry:
        """Roots from settings: explicit ``skills_dir``, else project + home skills."""
        if settings is None:
            from agentkit.config import get_settings

            settings = get_settings()
        roots: list[Path] = []
        configured = getattr(settings, "skills_dir", None)
        if configured:
            roots.append(Path(configured).expanduser())
        else:
            roots.append(Path.cwd() / DEFAULT_SKILL_DIR)
            home = getattr(settings, "home", None)
            if home is not None:
                roots.append(Path(home) / DEFAULT_SKILL_DIR)
        return cls(roots)

    # -- mutation -------------------------------------------------------
    def register(self, skill: Skill) -> Skill:
        self._skills[skill.name] = skill
        return skill

    def discover(self, *, reload: bool = False) -> SkillRegistry:
        """Scan every root for ``*/SKILL.md`` (and a root-level ``SKILL.md``)."""
        if reload:
            self._skills.clear()
        for root in self.roots:
            if not root.is_dir():
                continue
            if (root / SKILL_FILENAME).is_file():
                self._try_register(root / SKILL_FILENAME)
            for skill_md in sorted(root.glob(f"*/{SKILL_FILENAME}")):
                self._try_register(skill_md)
        return self

    def _try_register(self, skill_md: Path) -> None:
        try:
            self.register(load_skill_file(skill_md))
        except Exception:  # pragma: no cover - a malformed skill must not stop discovery
            log.exception("skipping unreadable skill at %s", skill_md)

    # -- reads ----------------------------------------------------------
    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return [self._skills[key] for key in sorted(self._skills)]

    def names(self) -> list[str]:
        return sorted(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self) -> Iterator[Skill]:
        return iter(self.all())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._skills

    # -- rendering ------------------------------------------------------
    def index(self) -> str:
        """A compact ``- name: description`` listing for the instructions."""
        skills = self.all()
        if not skills:
            return ""
        lines = [f"- {skill.name}: {skill.description}".rstrip(": ") for skill in skills]
        return "Available skills (load one with `load_skill` when relevant):\n" + "\n".join(lines)

    def load(self, name: str) -> str:
        skill = self.get(name)
        if skill is None:
            return f"No skill named {name!r}. Available: {', '.join(self.names()) or '(none)'}."
        return skill.render()

    def read_file(self, name: str, relative: str) -> str:
        skill = self.get(name)
        if skill is None:
            return f"No skill named {name!r}."
        try:
            return skill.read(relative)
        except (OSError, ValueError) as exc:
            return f"Could not read {relative!r} from skill {name!r}: {exc}"

    def tool_policy(self, *, extra: Sequence[str] = ()) -> Any:
        """A ``ToolPolicy`` allowing the union of every skill's ``allowed-tools``.

        Returns an allow-everything policy when no skill declares any tools.
        """
        from agentkit.policy import ToolPolicy

        allowed: set[str] = set(extra)
        for skill in self.all():
            allowed.update(skill.allowed_tools)
        return ToolPolicy(allow=allowed or None)


__all__ = [
    "DEFAULT_SKILL_DIR",
    "SKILL_FILENAME",
    "Skill",
    "SkillRegistry",
    "load_skill_file",
    "parse_front_matter",
]
