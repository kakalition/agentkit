"""A sandboxed workspace, backed by PydanticAI's workspace layer.

Rather than re-implementing path confinement, read-only enforcement, and
subprocess execution, agentkit delegates to ``pydantic_ai.workspaces`` — the
same well-tested primitives PydanticAI uses:

* ``LocalWorkspaceBackend`` runs commands rooted at the workspace directory and
  resolves paths within it.
* ``ReadOnlyWorkspace`` blocks every write when ``read_only=True``.

:class:`Sandbox` is a thin, ergonomic async wrapper over that backend; wire it
into an agent with the builder's ``.workspace(...)``, which adds
``read_file``/``list_files``/``write_file``/``run_command`` tools::

    from agentkit import Agent, Sandbox

    agent = Agent.make("coder").instructions("…").workspace(Sandbox("./work")).build()

Note: like PydanticAI's ``LocalWorkspace``, this does **not** isolate the process
from the host — use a container/VM workspace for untrusted code.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic_ai.workspaces import (
    CommandResult,
    FileEntry,
    LocalWorkspaceBackend,
    ReadOnlyWorkspace,
    Workspace,
    WorkspaceError,
    WorkspaceReadOnlyError,
)

__all__ = [
    "CommandResult",
    "FileEntry",
    "Sandbox",
    "SandboxError",
    "WorkspaceError",
    "WorkspaceReadOnlyError",
    "render_command",
]

# agentkit's historical name for a workspace error.
SandboxError = WorkspaceError


def render_command(result: CommandResult) -> str:
    """Render a :class:`CommandResult` for a tool response."""
    parts = [f"exit {result.exit_code}"]
    if result.stdout:
        parts.append(result.stdout.rstrip())
    if result.stderr:
        parts.append(f"[stderr]\n{result.stderr.rstrip()}")
    return "\n".join(parts)


class Sandbox:
    """A root-confined workspace over ``pydantic_ai.workspaces``."""

    def __init__(
        self,
        root: str | Path,
        *,
        read_only: bool = False,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.read_only = read_only
        self.timeout = timeout
        backend = LocalWorkspaceBackend(self.root, env=env)
        workspace = Workspace(backend)
        self._ws: Any = ReadOnlyWorkspace(workspace) if read_only else workspace

    # -- paths ----------------------------------------------------------
    def _rel(self, path: str) -> str:
        try:
            return os.path.relpath(path, self.root)
        except ValueError:  # pragma: no cover - different drives on Windows
            return path

    # -- operations -----------------------------------------------------
    async def read(self, path: str | Path) -> str:
        return await self._ws.read_text(str(path))

    async def write(self, path: str | Path, content: str) -> str:
        await self._ws.write_text(str(path), content)
        return str(path)

    async def list(self, path: str | Path = ".") -> list[str]:
        entries = await self._ws.list_dir(str(path))
        return sorted(self._rel(entry.path) for entry in entries)

    async def exists(self, path: str | Path) -> bool:
        return await self._ws.exists(str(path))

    async def run(self, command: str | Sequence[str], *, timeout: float | None = None) -> CommandResult:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        if not argv:
            raise SandboxError("empty command")
        return await self._ws.run(argv, timeout=timeout or self.timeout)


def coerce_sandbox(value: Any, *, read_only: bool = False) -> Sandbox:
    """Accept a ``Sandbox`` or a path/root and return a ``Sandbox``."""
    if isinstance(value, Sandbox):
        return value
    return Sandbox(value, read_only=read_only)
