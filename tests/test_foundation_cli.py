from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.foundation.commands import load_bootstrap
from agentkit.foundation.generators import KINDS, generate, target_path


def test_generators_write_valid_python(tmp_path: Path):
    for kind in KINDS:
        written = generate(kind, "My-Thing", directory=tmp_path)
        assert written.exists()
        compile(written.read_text(), str(written), "exec")
        assert target_path(kind, "My-Thing", tmp_path) == written


def test_generator_overwrite_guard(tmp_path: Path):
    generate("tool", "add_note", directory=tmp_path)
    try:
        generate("tool", "add_note", directory=tmp_path)
    except FileExistsError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected FileExistsError")
    generate("tool", "add_note", directory=tmp_path, force=True)


def test_generated_provider_names_classes(tmp_path: Path):
    path = generate("provider", "notes", directory=tmp_path)
    namespace: dict = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    assert "NotesProvider" in namespace
    compiled_model = generate("model", "note", directory=tmp_path)
    exec(compile(compiled_model.read_text(), str(compiled_model), "exec"), {})


def test_make_agent_is_discoverable(tmp_path: Path):
    path = generate("agent", "Notes", directory=tmp_path)
    assert path == tmp_path / "app" / "Agents" / "Notes.py"
    assert "class Notes(AgentDefinition)" in path.read_text()


def test_unknown_generator_raises():
    try:
        generate("nope", "x")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_cli_make_tool(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli_app, ["make:tool", "add_note", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "app" / "Tools" / "add_note.py").exists()

    again = runner.invoke(cli_app, ["make:tool", "add_note", "--path", str(tmp_path)])
    assert again.exit_code == 1


def test_cli_about():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["about"])
    assert result.exit_code == 0
    assert "agentkit" in result.stdout


def test_load_bootstrap_from_env(tmp_path: Path, monkeypatch):
    module = tmp_path / "my_bootstrap_mod.py"
    module.write_text("from agentkit import App\napp = App('booted', discover=False)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("AGENTKIT_BOOTSTRAP", "my_bootstrap_mod:app")
    loaded = load_bootstrap()
    assert loaded.name == "booted"


def test_cli_inspect_against_bootstrap(tmp_path: Path, monkeypatch):
    module = tmp_path / "inspect_bootstrap_mod.py"
    module.write_text(
        "from agentkit import App\n"
        "from agentkit.foundation.agent import Agent\n"
        "app = App('inspected', discover=False)\n"
        "app.agent(Agent.make('inspected').instructions('x').output(str))\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["inspect", "--bootstrap", "inspect_bootstrap_mod:app"])
    assert result.exit_code == 0, result.stdout
    assert "inspected" in result.stdout


def test_load_bootstrap_resolves_from_cwd(tmp_path: Path, monkeypatch):
    """`agentkit serve` should import bootstrap.py from the project root."""
    import sys

    monkeypatch.delenv("AGENTKIT_BOOTSTRAP", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bootstrap.py").write_text(
        "from agentkit import App\napp = App('from-cwd', discover=False)\n"
    )
    sys.modules.pop("bootstrap", None)
    # Ensure cwd is not already importable before the call.
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))])

    loaded = load_bootstrap()
    assert loaded.name == "from-cwd"
    sys.modules.pop("bootstrap", None)
