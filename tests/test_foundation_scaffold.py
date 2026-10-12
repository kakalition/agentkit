from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentkit import package_name, scaffold_project
from agentkit.cli import app as cli_app


def test_package_name_normalisation():
    assert package_name("my-agent") == "my_agent"
    assert package_name("My Agent!") == "my_agent"
    assert package_name("123app") == "app_123app"
    assert package_name("...") == "app"


def test_scaffold_creates_runnable_project(tmp_path: Path):
    target = scaffold_project("demo-app", tmp_path)

    assert target == tmp_path / "demo-app"
    for relative in [
        "bootstrap.py",
        "pyproject.toml",
        "README.md",
        ".env.example",
        ".gitignore",
        "SOUL.md",
        "conftest.py",
        "app/__init__.py",
        "app/config.py",
        "app/models.py",
        "app/providers.py",
        "app/tools.py",
        "skills/hello/SKILL.md",
        "prompts/system.md",
        "config/app.py",
        "evals/smoke.yaml",
        "tests/test_smoke.py",
    ]:
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


def test_scaffolded_project_imports_and_boots(tmp_path: Path):
    """The generated project boots and its own test suite passes (isolated)."""
    import subprocess
    import sys

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
    assert (tmp_path / "cli-app" / "app" / "providers.py").is_file()
    assert "Created" in result.output


def test_cli_new_refuses_existing(tmp_path: Path):
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "x.txt").write_text("x")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["new", "busy", "--path", str(tmp_path), "--no-git"])
    assert result.exit_code == 1
