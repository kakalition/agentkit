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
import shlex
import shutil
import sys
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext

from agentkit.capability import Capability
from agentkit.contracts.codeexec import CodeExecutor, HibernatingExecutor
from agentkit.errors import ConfigurationError, InvalidInput
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import CodeExecDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "CodeExecManager",
    "CodeExecutor",
    "DaytonaExecutor",
    "DockerExecutor",
    "E2BExecutor",
    "ExecResult",
    "HibernatingExecutor",
    "JupyterExecutor",
    "LocalSubprocessExecutor",
    "ModalExecutor",
    "SingularityExecutor",
    "SSHExecutor",
    "VercelExecutor",
    "CodeExecutorCapability",
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


class _Hibernating:
    """No-op ``hibernate``/``wake`` defaults for serverless-capable backends."""

    async def hibernate(self) -> None:
        return None

    async def wake(self) -> None:
        return None


class JupyterExecutor(_Hibernating):
    """Run code in a Jupyter kernel (needs the ``jupyter`` extra)."""

    def __init__(self, *, kernel_name: str = "python3", default_timeout: float = 30.0) -> None:
        self.kernel_name = kernel_name
        self.default_timeout = default_timeout

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            import jupyter_client
        except ImportError as exc:
            raise _missing_extra("jupyter") from exc
        limit = float(timeout if timeout is not None else self.default_timeout)
        return await asyncio.to_thread(self._run_sync, jupyter_client, code, limit)

    def _run_sync(self, jupyter_client: Any, code: str, timeout: float) -> ExecResult:  # pragma: no cover
        manager = jupyter_client.KernelManager(kernel_name=self.kernel_name)
        manager.start_kernel()
        client = manager.client()
        client.start_channels()
        try:
            client.wait_for_ready(timeout=timeout)
            msg_id = client.execute(code)
            out: list[str] = []
            err: list[str] = []
            error: str | None = None
            while True:
                message = client.get_iopub_msg(timeout=timeout)
                if message.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                kind = message["header"]["msg_type"]
                content = message["content"]
                if kind == "stream":
                    (out if content.get("name") == "stdout" else err).append(content.get("text", ""))
                elif kind == "error":
                    error = "\n".join(content.get("traceback", [])) or str(content.get("evalue", ""))
                elif kind == "status" and content.get("execution_state") == "idle":
                    break
            return ExecResult(
                stdout="".join(out), stderr=error or "".join(err), exit_code=1 if error else 0
            )
        finally:
            client.stop_channels()
            manager.shutdown_kernel(now=True)


class E2BExecutor(_Hibernating):
    """Run code on E2B (needs the ``e2b`` extra); supports hibernate/wake."""

    def __init__(self, *, api_key: str | None = None, sandbox: Any = None) -> None:
        self.api_key = api_key
        self._sandbox = sandbox

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError as exc:
            raise _missing_extra("e2b") from exc
        return await asyncio.to_thread(self._run_sync, Sandbox, code)

    def _run_sync(self, sandbox_cls: Any, code: str) -> ExecResult:  # pragma: no cover - needs e2b
        if self._sandbox is None:
            self._sandbox = sandbox_cls(api_key=self.api_key) if self.api_key else sandbox_cls()
        execution = self._sandbox.run_code(code)
        logs = execution.logs
        return ExecResult(
            stdout="\n".join(getattr(logs, "stdout", []) or []),
            stderr="\n".join(getattr(logs, "stderr", []) or []),
            exit_code=1 if getattr(execution, "error", None) else 0,
        )

    async def hibernate(self) -> None:  # pragma: no cover - needs e2b
        if self._sandbox is not None and hasattr(self._sandbox, "pause"):
            await asyncio.to_thread(self._sandbox.pause)

    async def wake(self) -> None:  # pragma: no cover - needs e2b
        try:
            from e2b_code_interpreter import Sandbox
        except ImportError as exc:
            raise _missing_extra("e2b") from exc
        if self._sandbox is not None and hasattr(self._sandbox, "connect"):
            self._sandbox = await asyncio.to_thread(Sandbox.connect, self._sandbox.sandbox_id)


class SSHExecutor(_Hibernating):
    """Run code on a remote host over SSH (needs the ``ssh`` extra: paramiko)."""

    def __init__(
        self,
        host: str | None = None,
        *,
        user: str | None = None,
        key_filename: str | None = None,
        port: int = 22,
        default_timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.user = user
        self.key_filename = key_filename
        self.port = port
        self.default_timeout = default_timeout

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            import paramiko
        except ImportError as exc:
            raise _missing_extra("ssh") from exc
        host = options.get("host") or self.host
        if not host:
            raise ConfigurationError("SSHExecutor needs a host (pass host= or SSHExecutor(host))")
        limit = float(timeout if timeout is not None else self.default_timeout)
        return await asyncio.to_thread(self._run_sync, paramiko, host, code, limit)

    def _run_sync(self, paramiko: Any, host: str, code: str, timeout: float) -> ExecResult:  # pragma: no cover
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            host, port=self.port, username=self.user, key_filename=self.key_filename, timeout=timeout
        )
        try:
            _, stdout, stderr = client.exec_command(f"python3 -c {shlex.quote(code)}", timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            exit_code = stdout.channel.recv_exit_status()
        finally:
            client.close()
        return ExecResult(stdout=out, stderr=err, exit_code=int(exit_code))


class ModalExecutor(_Hibernating):
    """Run code in a Modal sandbox (needs the ``modal`` extra)."""

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            import modal
        except ImportError as exc:
            raise _missing_extra("modal") from exc
        return await asyncio.to_thread(self._run_sync, modal, code)

    def _run_sync(self, modal: Any, code: str) -> ExecResult:  # pragma: no cover - needs modal
        app = modal.App.lookup("agentkit-exec", create_if_missing=True)
        sandbox = modal.Sandbox.create(app=app, image=modal.Image.debian_slim())
        try:
            process = sandbox.exec("python", "-c", code)
            return ExecResult(
                stdout=process.stdout.read(),
                stderr=process.stderr.read(),
                exit_code=int(process.wait() or 0),
            )
        finally:
            sandbox.terminate()


class DaytonaExecutor(_Hibernating):
    """Run code in a Daytona sandbox (needs the ``daytona`` extra)."""

    def __init__(self, *, api_key: str | None = None, image: str = "python:3.12-slim") -> None:
        self.api_key = api_key
        self.image = image

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            from daytona import Daytona
        except ImportError as exc:
            raise _missing_extra("daytona") from exc
        return await asyncio.to_thread(self._run_sync, Daytona, code)

    def _run_sync(self, daytona_cls: Any, code: str) -> ExecResult:  # pragma: no cover - needs daytona
        client = daytona_cls(api_key=self.api_key) if self.api_key else daytona_cls()
        sandbox = client.create()
        try:
            response = sandbox.process.code_run(code)
            return ExecResult(stdout=str(getattr(response, "result", response)))
        finally:
            client.delete(sandbox)


class VercelExecutor(_Hibernating):
    """Run code on Vercel Sandbox (needs the ``vercel`` extra / a configured sandbox)."""

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        try:
            import vercel  # noqa: F401
        except ImportError as exc:
            raise _missing_extra("vercel") from exc
        raise ConfigurationError(
            "the vercel executor needs a configured sandbox; install the vercel SDK and "
            "provide a sandbox via options"
        )


class SingularityExecutor(_Hibernating):
    """Run code in a Singularity/Apptainer container (needs ``singularity`` on PATH)."""

    def __init__(self, image: str, *, default_timeout: float = 30.0) -> None:
        self.image = image
        self.default_timeout = default_timeout

    async def run(
        self, code: str, *, language: str = "python", timeout: float | None = None, **options: Any
    ) -> ExecResult:
        if language not in {"python", "py"}:
            raise InvalidInput(f"unsupported language {language!r}; only python is supported")
        binary = shutil.which("singularity") or shutil.which("apptainer")
        if binary is None:
            raise _missing_extra("singularity")
        proc = await asyncio.create_subprocess_exec(
            binary,
            "exec",
            self.image,
            "python3",
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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


class CodeExecManager(Manager):
    """Resolves the configured code executor (``code_executor_driver``, default ``local``)."""

    kind = DriverKind.CODEEXEC
    default_driver = CodeExecDriver.LOCAL

    @property
    def setting_name(self) -> str:
        # The kind is ``codeexec`` but the setting is ``code_executor_driver``.
        return "code_executor_driver"


@register_driver(DriverKind.CODEEXEC, CodeExecDriver.LOCAL)
class LocalExecutorDriver(Driver):
    def build(self) -> LocalSubprocessExecutor:
        return LocalSubprocessExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.DOCKER)
class DockerExecutorDriver(Driver):
    def build(self) -> DockerExecutor:
        return DockerExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.JUPYTER)
class JupyterExecutorDriver(Driver):
    def build(self) -> JupyterExecutor:
        return JupyterExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.E2B)
class E2bExecutorDriver(Driver):
    def build(self) -> E2BExecutor:
        return E2BExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.SSH)
class SshExecutorDriver(Driver):
    def build(self) -> SSHExecutor:
        app = self.app
        return SSHExecutor(getattr(app.settings, "ssh_host", None))
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.MODAL)
class ModalExecutorDriver(Driver):
    def build(self) -> ModalExecutor:
        return ModalExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.DAYTONA)
class DaytonaExecutorDriver(Driver):
    def build(self) -> DaytonaExecutor:
        return DaytonaExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.VERCEL)
class VercelExecutorDriver(Driver):
    def build(self) -> VercelExecutor:
        return VercelExecutor()
@register_driver(DriverKind.CODEEXEC, CodeExecDriver.SINGULARITY)
class SingularityExecutorDriver(Driver):
    def build(self) -> SingularityExecutor:
        app = self.app
        return SingularityExecutor(getattr(app.settings, "singularity_image", "python:3.12-slim"))
class CodeExecutorCapability(Capability):
    name = "code_executor"

    def __init__(self, executor: Any = None) -> None:
        self.executor = executor

    def install(self, agent: Any) -> Any:
        executor = self.executor

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