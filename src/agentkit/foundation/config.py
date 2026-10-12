"""Per-concern configuration sections.

Applications declare small schemas and agentkit layers them over the process
environment:

    from agentkit import Section

    class MemorySection(Section):
        env_prefix = "AGENTKIT_MEMORY_"
        enabled: bool = True

    app.config("memory", MemorySection)

Resolution precedence is **defaults < config/<name>.py < environment**. A
``config/<name>.py`` module exposes its values as a module-level ``config`` dict::

    # config/memory.py
    config = {"enabled": False}
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

CONFIG_DIR_ENV = "AGENTKIT_CONFIG_DIR"


class Section(BaseModel):
    """Base class for a per-concern config section."""

    model_config = ConfigDict(extra="ignore")

    env_prefix: ClassVar[str] = ""

    @classmethod
    def env_name(cls, field: str) -> str:
        return f"{cls.env_prefix}{field}".upper()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> dict[str, str]:
        environ = os.environ if environ is None else environ
        data: dict[str, str] = {}
        for field in cls.model_fields:
            key = cls.env_name(field)
            if key in environ:
                data[field] = environ[key]
        return data

    @classmethod
    def resolve(
        cls,
        file_values: Mapping[str, Any] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> Section:
        """Merge defaults, then file values, then environment (highest wins)."""
        data: dict[str, Any] = cls().model_dump()
        if file_values:
            data.update({key: value for key, value in file_values.items() if value is not None})
        data.update(cls.from_env(environ))
        return cls(**data)


def config_directory(directory: str | Path | None = None) -> Path:
    if directory is not None:
        return Path(directory)
    env = os.environ.get(CONFIG_DIR_ENV)
    if env:
        return Path(env).expanduser()
    return Path.cwd() / "config"


def load_config_file(name: str, *, directory: str | Path | None = None) -> dict[str, Any]:
    """Read ``config/<name>.py``'s module-level ``config`` dict (empty if absent)."""
    path = config_directory(directory) / f"{name}.py"
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location(f"agentkit_config_{name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = getattr(module, "config", None)
    if isinstance(values, Mapping):
        return dict(values)
    return {}


def resolve_section(
    name: str,
    schema: type[Section],
    *,
    directory: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Any:
    """Resolve a section schema for ``name`` with file + env layering."""
    if issubclass(schema, Section):
        return schema.resolve(load_config_file(name, directory=directory), environ=environ)
    return schema()


__all__ = [
    "CONFIG_DIR_ENV",
    "Section",
    "config_directory",
    "load_config_file",
    "resolve_section",
]
