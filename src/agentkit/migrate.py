"""Import an existing Claw/OpenClaw hub into an agentkit agent home.

The importer is deliberately tolerant: it recognises several common layouts and
normalizes whatever it finds, reporting what it imported and warning about
anything it could not read. Nothing in the source tree is modified.

Recognised source entries under ``source``:

* ``config.json`` — written to ``<target>/import/config.json``
* ``memories.jsonl`` / ``memory.jsonl`` / ``memory/*.md`` — normalized to
  ``<target>/import/memories.jsonl``
* ``skills/**`` — copied verbatim (a tree of ``SKILL.md`` folders)
* ``schedules.json`` — written to ``<target>/import/schedules.json``
* ``channels.json`` — written to ``<target>/import/channels.json``
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentkit.errors import InvalidInput

__all__ = ["MigrationReport", "migrate_openclaw"]

_MEMORY_FILES = ("memories.jsonl", "memory.jsonl")
_MEMORY_DIRS = ("memory", "memories")


@dataclass
class MigrationReport:
    """What a migration imported (and anything it could not)."""

    source: str
    target: str
    dry_run: bool = False
    config: bool = False
    memories: int = 0
    skills: int = 0
    schedules: int = 0
    channels: int = 0
    files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"migrate openclaw: {self.source} -> {self.target}"
            + (" (dry run)" if self.dry_run else ""),
            f"  config: {'imported' if self.config else 'none'}",
            f"  memories: {self.memories}",
            f"  skills: {self.skills}",
            f"  schedules: {self.schedules}",
            f"  channels: {self.channels}",
        ]
        lines.extend(f"  - wrote {path}" for path in self.files)
        lines.extend(f"  ! {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise InvalidInput(f"{path} is not valid JSON: {exc}") from exc


def _memory_items(source: Path) -> list[str]:
    items: list[str] = []
    for name in _MEMORY_FILES:
        path = source / name
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    items.append(line)
                    continue
                if isinstance(parsed, dict):
                    items.append(str(parsed.get("content") or parsed.get("text") or parsed))
                else:
                    items.append(str(parsed))
    for dirname in _MEMORY_DIRS:
        directory = source / dirname
        if directory.is_dir():
            for path in sorted(directory.glob("*.md")):
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    items.append(text)
    return [item for item in items if item]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def migrate_openclaw(source: str | Path, *, target: str | Path, dry_run: bool = False) -> MigrationReport:
    """Import ``source`` (an OpenClaw hub) into the agent home ``target``."""
    src = Path(source).expanduser()
    if not src.is_dir():
        raise InvalidInput(f"source {source!r} is not a directory")
    dst = Path(target).expanduser()
    report = MigrationReport(source=str(src), target=str(dst), dry_run=dry_run)
    import_dir = dst / "import"

    # config
    config = next((src / name for name in ("config.json",) if (src / name).is_file()), None)
    if config is not None:
        report.config = True
        if not dry_run:
            _write(import_dir / "config.json", config.read_text(encoding="utf-8"))
            report.files.append(str(import_dir / "config.json"))
    elif (src / "config.yaml").is_file():
        report.warnings.append("config.yaml found; convert it to config.json to import")

    # memories
    memories = _memory_items(src)
    report.memories = len(memories)
    if memories and not dry_run:
        _write(import_dir / "memories.jsonl", "\n".join(json.dumps(m) for m in memories))
        report.files.append(str(import_dir / "memories.jsonl"))

    # skills
    skills_dir = src / "skills"
    if skills_dir.is_dir():
        skill_dirs = [path.parent for path in skills_dir.rglob("SKILL.md")]
        report.skills = len(skill_dirs)
        if not dry_run and skill_dirs:
            target_skills = dst / "skills"
            for skill_dir in skill_dirs:
                destination = target_skills / skill_dir.name
                shutil.copytree(skill_dir, destination, dirs_exist_ok=True)
                report.files.append(str(destination))

    # schedules
    schedules = src / "schedules.json"
    if schedules.is_file():
        parsed = _read_json(schedules)
        report.schedules = len(parsed) if isinstance(parsed, list) else 1
        if not dry_run:
            _write(import_dir / "schedules.json", json.dumps(parsed, indent=2))
            report.files.append(str(import_dir / "schedules.json"))

    # channels
    channels = src / "channels.json"
    if channels.is_file():
        parsed = _read_json(channels)
        report.channels = len(parsed) if isinstance(parsed, dict) else 1
        if not dry_run:
            _write(import_dir / "channels.json", json.dumps(parsed, indent=2))
            report.files.append(str(import_dir / "channels.json"))

    if not any((report.config, report.memories, report.skills, report.schedules, report.channels)):
        report.warnings.append("no recognisable OpenClaw files found under the source")
    return report
