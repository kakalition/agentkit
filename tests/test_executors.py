from __future__ import annotations

from pathlib import Path

import pytest

from agentkit import AgentSettings
from agentkit.contracts.codeexec import CodeExecutor, HibernatingExecutor
from agentkit.contracts.storage import FileSystem
from agentkit.errors import ConfigurationError, InvalidInput
from agentkit.executors import (
    DaytonaExecutor,
    DockerExecutor,
    E2BExecutor,
    JupyterExecutor,
    LocalSubprocessExecutor,
    ModalExecutor,
    SingularityExecutor,
    SSHExecutor,
    VercelExecutor,
)
from agentkit.foundation.application import App
from agentkit.foundation.storage import MemoryFilesystem, S3FileSystem


def _settings(tmp_path: Path, **overrides) -> AgentSettings:
    return AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash", **overrides)


def test_executors_conform_to_contract():
    for executor in (
        LocalSubprocessExecutor(),
        DockerExecutor(),
        JupyterExecutor(),
        E2BExecutor(),
        SSHExecutor(),
        ModalExecutor(),
        DaytonaExecutor(),
        VercelExecutor(),
        SingularityExecutor("img"),
    ):
        assert isinstance(executor, CodeExecutor)


def test_hibernating_capability_is_optional():
    assert isinstance(E2BExecutor(), HibernatingExecutor)
    assert isinstance(SSHExecutor(), HibernatingExecutor)
    assert not isinstance(LocalSubprocessExecutor(), HibernatingExecutor)


async def test_local_executor_runs_code():
    result = await LocalSubprocessExecutor().run("print('hi')")
    assert result.ok and "hi" in result.stdout


async def test_local_executor_rejects_other_languages():
    with pytest.raises(InvalidInput):
        await LocalSubprocessExecutor().run("puts 'x'", language="ruby")


@pytest.mark.parametrize(
    ("executor", "extra"),
    [
        (JupyterExecutor(), "jupyter"),
        (E2BExecutor(), "e2b"),
        (SSHExecutor("host"), "ssh"),
        (ModalExecutor(), "modal"),
        (DaytonaExecutor(), "daytona"),
        (VercelExecutor(), "vercel"),
        (SingularityExecutor("img"), "singularity"),
    ],
)
async def test_missing_extra_names_the_extra(executor, extra):
    with pytest.raises(ConfigurationError) as excinfo:
        await executor.run("print(1)")
    assert extra in str(excinfo.value)


def test_code_executor_driver_selection(tmp_path: Path):
    app = App(name="c", settings=_settings(tmp_path), discover=False)
    assert isinstance(app.code_executor, LocalSubprocessExecutor)

    ssh = App(
        name="c", settings=_settings(tmp_path, code_executor_driver="ssh"), discover=False
    )
    assert isinstance(ssh.code_executor, SSHExecutor)


def test_s3_filesystem_conforms_and_lazy_imports(tmp_path: Path):
    fs = S3FileSystem("my-bucket", prefix="artifacts")
    assert isinstance(fs, FileSystem)
    # Constructing must not require boto3; first use raises naming the extra.
    with pytest.raises(ConfigurationError) as excinfo:
        fs.exists("x.txt")
    assert "s3" in str(excinfo.value)


def test_s3_storage_driver_requires_bucket(tmp_path: Path):
    app = App(name="s", settings=_settings(tmp_path, storage_driver="s3"), discover=False)
    with pytest.raises(ConfigurationError):
        _ = app.storage

    configured = App(
        name="s",
        settings=_settings(tmp_path, storage_driver="s3", s3_bucket="b"),
        discover=False,
    )
    assert isinstance(configured.storage, S3FileSystem)


def test_storage_and_executor_fake_backends_conform():
    assert isinstance(MemoryFilesystem(), FileSystem)

    class FakeExecutor:
        async def run(self, code, **options):  # noqa: ANN001, ANN003, ANN201
            return code

    assert isinstance(FakeExecutor(), CodeExecutor)
