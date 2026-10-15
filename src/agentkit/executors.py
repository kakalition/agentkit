"""Code execution: a sandbox contract + drivers (local subprocess by default).

    from agentkit.executors import attach_code_executor

    attach_code_executor(agent)   # registers an approval-gated ``run_code`` tool

The default ``local`` driver runs code in a **restricted** subprocess of the
current interpreter — it is not a security boundary. Use ``docker``/``jupyter``/
``e2b`` (optional extras) for real isolation; those raise
:class:`~agentkit.errors.ConfigurationError` naming the extra when missing.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext

from agentkit.contracts.codeexec import CodeExecutor
from agentkit.errors import ConfigurationError, InvalidInput
from agentkit.support import register_driver
from agentkit.support.kinds import CodeExecDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "CodeExecManager",
    "CodeExecutor",
    "DockerExecutor",
    "E2BExecutor",
    "ExecResult",
    "JupyterExecutor",
    "LocalSubprocessExecutor",
    "attach_code_executor",
]


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def render(self) -> str:
        parts = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.stderr:
            parts.append(f"[stderr]\n{self.stderr.rstrip()}")
        parts.append(f"[exit {self.exit_code}]")
        return "\n".join(parts)


class LocalSubprocessExecutor:
    """The default executor: a subprocess of the current Python interpreter.

    A practical convenience, **not** a security boundary — gate ``run_code`` with
    approval and (for untrusted input) prefer a containerized driver.
    """

    def __init__(self, *, python: str | None = None, default_timeout: float = 10.0) -> None:
        self.python = python or sys.executable
        self.default_timeout = default_timeout

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        proc = await asyncio.create_subprocess_exec(
            self.python,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=options.get("cwd"),
        )
        limit = float(timeout if timeout is not None else self.default_timeout)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=limit)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecResult(stderr=f"timed out after {limit}s", exit_code=-1)
        return ExecResult(
            stdout=out.decode("utf-8", errors="replace"),
            stderr=err.decode("utf-8", errors="replace"),
            exit_code=int(proc.returncode or 0),
        )


def _missing_extra(extra: str) -> ConfigurationError:
    return ConfigurationError(
        f"this code-execution driver needs the {extra!r} extra "
        f"(pip install agentkit[{extra}])"
    )


class DockerExecutor:
    """Run code inside a Docker container (needs the ``docker`` extra)."""

    def __init__(self, image: str = "python:3.12-slim") -> None:
        self.image = image

    async def run(self, code: str, **options: Any) -> ExecResult:  # pragma: no cover - optional
        try:
            import docker
        except ImportError as exc:
            raise _missing_extra("docker") from exc
        return await asyncio.to_thread(self._run_sync, docker, code, options)

    def _run_sync(self, docker: Any, code: str, options: dict[str, Any]) -> ExecResult:  # pragma: no cover
        client = docker.from_env()
        result = client.containers.run(
            self.image, ["python", "-c", code], remove=True, stdout=True, stderr=True
        )
        return ExecResult(stdout=result.decode("utf-8", errors="replace"))


class JupyterExecutor:
    """Run code in a Jupyter kernel (needs the ``jupyter`` extra)."""

    async def run(self, code: str, **options: Any) -> ExecResult:  # pragma: no cover - optional
        try:
            import jupyter_client  # noqa: F401
        except ImportError as exc:
            raise _missing_extra("jupyter") from exc
        raise ConfigurationError("the jupyter executor is not implemented yet")


class E2BExecutor:
    """Run code on E2B (needs the ``e2b`` extra)."""

    async def run(self, code: str, **options: Any) -> ExecResult:  # pragma: no cover - optional
        try:
            import e2b  # noqa: F401
        except ImportError as exc:
            raise _missing_extra("e2b") from exc
        raise ConfigurationError("the e2b executor is not implemented yet")


class CodeExecManager(Manager):
    """Resolves the configured code executor (``code_executor_driver``, default ``local``)."""

    kind = DriverKind.CODEEXEC
    default_driver = CodeExecDriver.LOCAL


@register_driver(DriverKind.CODEEXEC, CodeExecDriver.LOCAL)
def _local_executor_driver(app: Any) -> LocalSubprocessExecutor:
    return LocalSubprocessExecutor()


@register_driver(DriverKind.CODEEXEC, CodeExecDriver.DOCKER)
def _docker_executor_driver(app: Any) -> DockerExecutor:
    return DockerExecutor()


@register_driver(DriverKind.CODEEXEC, CodeExecDriver.JUPYTER)
def _jupyter_executor_driver(app: Any) -> JupyterExecutor:
    return JupyterExecutor()


@register_driver(DriverKind.CODEEXEC, CodeExecDriver.E2B)
def _e2b_executor_driver(app: Any) -> E2BExecutor:
    return E2BExecutor()


def attach_code_executor(agent: Any, *, executor: Any = None) -> Any:
    """Register an approval-gated ``run_code`` tool on a built agent (idempotent)."""
    if getattr(agent, "_agentkit_code_attached", False):
        return agent
    fallback = executor if executor is not None else LocalSubprocessExecutor()

    def resolve(ctx: Any) -> Any:
        deps = getattr(ctx, "deps", None)
        extras = getattr(deps, "extras", None)
        if isinstance(extras, dict) and extras.get("code_executor") is not None:
            return extras["code_executor"]
        return fallback

    @agent.tool(requires_approval=True)
    async def run_code(
        ctx: RunContext[Any], code: str, language: str = "python", timeout: float = 10.0
    ) -> str:
        """Run a short snippet of code and return its output (requires approval).

        Args:
            code: The code to run.
            language: The language (only ``python`` is supported locally).
            timeout: Seconds before the run is killed.
        """
        result = await resolve(ctx).run(code, language=language, timeout=timeout)
        return result.render()

    agent._agentkit_code_attached = True  # type: ignore[attr-defined]
    return agent
