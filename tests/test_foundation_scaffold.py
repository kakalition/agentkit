from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentkit import package_name, scaffold_project
from agentkit.cli import app as cli_app

EXPECTED = [
    "bootstrap.py",
    "pyproject.toml",
    "README.md",
    ".env.example",
    ".gitignore",
    "SOUL.md",
    "conftest.py",
    "app/__init__.py",
    "app/config.py",
    "app/Agents/assistant.py",
    "app/Console/Kernel.py",
    "app/Console/Commands/PinNote.py",
    "app/Events/NoteSaved.py",
    "app/Jobs/SyncNotes.py",
    "app/Listeners/LogNoteSaved.py",
    "app/Middleware/Timing.py",
    "app/Models/Note.py",
    "app/Notifications/NoteSaved.py",
    "app/Policies/AssistantPolicy.py",
    "app/Providers/AppServiceProvider.py",
    "app/Providers/DriverServiceProvider.py",
    "app/Providers/EventServiceProvider.py",
    "app/Repositories/NoteRepository.py",
    "app/Repositories/__init__.py",
    "app/Rules/NonEmpty.py",
    "app/Services/NoteService.py",
    "app/Tools/notes.py",
    "config/app.py",
    "database/README.md",
    "evals/smoke.yaml",
    "prompts/system.md",
    "skills/hello/SKILL.md",
    "storage/.gitignore",
    "tests/test_smoke.py",
    "tests/test_note_service.py",
]


def test_package_name_normalisation():
    assert package_name("my-agent") == "my_agent"
    assert package_name("My Agent!") == "my_agent"
    assert package_name("123app") == "app_123app"
    assert package_name("...") == "app"


def test_scaffold_creates_full_project(tmp_path: Path):
    target = scaffold_project("demo-app", tmp_path)

    assert target == tmp_path / "demo-app"
    for relative in EXPECTED:
        assert (target / relative).is_file(), relative

    # No unresolved placeholders anywhere.
    for path in target.rglob("*"):
        if path.is_file():
            assert "{{" not in path.read_text(encoding="utf-8"), path


def test_scaffold_refuses_non_empty_without_force(tmp_path: Path):
    scaffold_project("demo", tmp_path)
    with pytest.raises(FileExistsError):
        scaffold_project("demo", tmp_path)
    scaffold_project("demo", tmp_path, force=True)


def test_scaffold_full_vs_minimal(tmp_path: Path):
    full = scaffold_project("full-app", tmp_path, full=True)
    assert (full / "app" / "Channels" / "Example.py").is_file()
    assert (full / "config" / "memory.py").is_file()
    assert "FullStackProvider" in (full / "bootstrap.py").read_text()
    assert "full = True" in (full / "app" / "Agents" / "assistant.py").read_text()

    minimal = scaffold_project("min-app", tmp_path, full=False)
    assert not (minimal / "app" / "Channels").exists()
    assert "FullStackProvider" not in (minimal / "bootstrap.py").read_text()


def test_scaffolded_project_boots_and_tests_pass(tmp_path: Path):
    """The generated project boots and its own pytest suite passes (isolated)."""
    target = scaffold_project("demo-app", tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=target,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_new(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli_app, ["new", "cli-app", "--path", str(tmp_path), "--no-git"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "cli-app" / "bootstrap.py").is_file()
    assert (tmp_path / "cli-app" / "app" / "Providers" / "AppServiceProvider.py").is_file()
    assert "Created" in result.output


def test_cli_new_refuses_existing(tmp_path: Path):
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "x.txt").write_text("x")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["new", "busy", "--path", str(tmp_path), "--no-git"])
    assert result.exit_code == 1
