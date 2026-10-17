"""Convention discovery for the Laravel-style front door.

Discovery runs at **boot** (never at import) and is deterministic (files are
scanned in sorted order). Each ``discover_*`` scans one conventional folder under
``base_path``, imports its modules (which must be import side-effect free), and
returns the classes/factories found:

==============  ==========================  ==========================
Concern         Folder                      Returned
==============  ==========================  ==========================
providers       ``app/Providers/``          ``Provider`` subclasses
agents          ``app/Agents/``             ``AgentDefinition`` subclasses
channels        ``app/Channels/``           ``(name, factory)`` pairs
commands        ``app/Console/Commands/``   ``Command`` subclasses
config          ``config/``                 ``{section: Section}``
==============  ==========================  ==========================

What ``Application.configure(...).withProviders(...)`` declares explicitly always
wins over what was discovered here.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentkit.foundation.agent import Agent, AgentDefinition
from agentkit.foundation.commands import Command
from agentkit.foundation.config import Section
from agentkit.foundation.provider import Provider

__all__ = [
    "CONVENTIONAL_DIRS",
    "discover_agents",
    "discover_channels",
    "discover_commands",
    "discover_config",
    "discover_listeners",
    "discover_policies",
    "discover_providers",
    "discover_repositories",
]

CONVENTIONAL_DIRS: dict[str, str] = {
    "providers": "app/Providers",
    "agents": "app/Agents",
    "channels": "app/Channels",
    "commands": "app/Console/Commands",
    "config": "config",
    "repositories": "app/Repositories",
    "policies": "app/Policies",
    "listeners": "app/Listeners",
}


def _root(base_path: str | Path) -> Path:
    root = Path(base_path).expanduser().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _module_specs(base_path: str | Path, relative: str) -> list[tuple[str, str]]:
    """``(module_stem, module_name)`` for each importable module in a folder."""
    root = _root(base_path)
    directory = root / relative
    if not directory.is_dir():
        return []
    specs: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = ".".join(path.relative_to(root).with_suffix("").parts)
        specs.append((path.stem, module_name))
    return specs


def _own(module: Any, obj: Any) -> bool:
    return getattr(obj, "__module__", None) == module.__name__


def _subclasses(module: Any, base: type, *, exclude: tuple[type, ...] = ()) -> list[type]:
    found: list[type] = []
    for obj in vars(module).values():
        if isinstance(obj, type) and obj not in exclude and issubclass(obj, base) and _own(module, obj):
            found.append(obj)
    return found


def discover_providers(base_path: str | Path = ".") -> list[type]:
    """``Provider`` subclasses declared under ``app/Providers/``."""
    found: list[type] = []
    for _stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["providers"]):
        found.extend(_subclasses(importlib.import_module(module_name), Provider))
    return found


def discover_agents(base_path: str | Path = ".") -> list[type[AgentDefinition]]:
    """``AgentDefinition`` subclasses declared under ``app/Agents/``."""
    found: list[type[AgentDefinition]] = []
    exclude = (AgentDefinition, Agent)
    for _stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["agents"]):
        module = importlib.import_module(module_name)
        found.extend(_subclasses(module, AgentDefinition, exclude=exclude))
    return found


def discover_commands(base_path: str | Path = ".") -> list[type]:
    """``Command`` subclasses declared under ``app/Console/Commands/``."""
    found: list[type] = []
    for _stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["commands"]):
        found.extend(_subclasses(importlib.import_module(module_name), Command))
    return found


def discover_channels(base_path: str | Path = ".") -> list[tuple[str, Callable[..., Any]]]:
    """``(name, ChannelClass)`` for each ``Channel`` subclass under ``app/Channels/``."""
    from agentkit.foundation.channels import Channel

    found: list[tuple[str, Callable[..., Any]]] = []
    for stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["channels"]):
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Channel)
                and obj is not Channel
                and getattr(obj, "__module__", None) == module.__name__
            ):
                instance = obj()
                found.append((instance.channel_name() or stem, obj))
    return found


def discover_config(base_path: str | Path = ".") -> dict[str, type]:
    """``{section: Section}`` for config modules that declare a ``Section`` subclass."""
    found: dict[str, type] = {}
    for stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["config"]):
        module = importlib.import_module(module_name)
        sections = _subclasses(module, Section, exclude=(Section,))
        if sections:
            found[stem] = sections[0]
    return found


def discover_policies(base_path: str | Path = ".") -> list[type]:
    """``Policy`` subclasses declared under ``app/Policies/``."""
    from agentkit.foundation.gate import Policy

    found: list[type] = []
    for _stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["policies"]):
        found.extend(_subclasses(importlib.import_module(module_name), Policy, exclude=(Policy,)))
    return found


def discover_listeners(base_path: str | Path = ".") -> list[type]:
    """``Listener`` subclasses declared under ``app/Listeners/``."""
    from agentkit.foundation.events import Listener

    found: list[type] = []
    for _stem, module_name in _module_specs(base_path, CONVENTIONAL_DIRS["listeners"]):
        found.extend(_subclasses(importlib.import_module(module_name), Listener, exclude=(Listener,)))
    return found


def discover_repositories(base_path: str | Path = ".") -> type | None:
    """The ``Repositories`` subclass under ``app/Repositories/`` (``__init__`` included)."""
    from agentkit.db.repositories import Repositories

    root = _root(base_path)
    directory = root / CONVENTIONAL_DIRS["repositories"]
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.py")):
        module_name = ".".join(path.relative_to(root).with_suffix("").parts)
        module = importlib.import_module(module_name)
        found = _subclasses(module, Repositories, exclude=(Repositories,))
        if found:
            return found[0]
    return None
