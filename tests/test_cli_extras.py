from __future__ import annotations

import json

from typer.testing import CliRunner

from agentkit.cli import app as cli_app
from agentkit.config import get_settings


def test_cli_knowledge_add_search_list(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("WEBUI_ENABLED", "false")
    get_settings.cache_clear()
    runner = CliRunner()

    added = runner.invoke(
        cli_app, ["knowledge", "add-text", "Mochi is a grey cat.", "--source", "pets"]
    )
    assert added.exit_code == 0, added.output
    assert "indexed" in added.output

    listed = runner.invoke(cli_app, ["knowledge", "list"])
    assert listed.exit_code == 0
    assert "pets" in listed.output

    found = runner.invoke(cli_app, ["knowledge", "search", "Mochi"])
    assert found.exit_code == 0
    assert "Mochi" in found.output

    get_settings.cache_clear()


def test_cli_eval_runs_suite(tmp_path, monkeypatch):
    module = tmp_path / "eval_bootstrap.py"
    module.write_text(
        "from agentkit import Agent, App\n"
        "from pydantic_ai.messages import ModelResponse, TextPart\n"
        "from pydantic_ai.models.function import FunctionModel\n"
        "app = App('ev', discover=False)\n"
        "app.agent(Agent.make('ev').instructions('x').output(str))\n"
        "app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart('4')]))\n",
        encoding="utf-8",
    )
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps({"cases": [{"name": "math", "input": "2+2?", "expect": "4"}]}),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(cli_app, ["eval", str(suite), "--bootstrap", "eval_bootstrap:app"])
    assert result.exit_code == 0, result.output
    assert "1/1 passed" in result.output


def test_cli_eval_failure_exits_nonzero(tmp_path, monkeypatch):
    module = tmp_path / "eval_fail_bootstrap.py"
    module.write_text(
        "from agentkit import Agent, App\n"
        "from pydantic_ai.messages import ModelResponse, TextPart\n"
        "from pydantic_ai.models.function import FunctionModel\n"
        "app = App('ev', discover=False)\n"
        "app.agent(Agent.make('ev').instructions('x').output(str))\n"
        "app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart('3')]))\n",
        encoding="utf-8",
    )
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps({"cases": [{"name": "math", "input": "2+2?", "expect": "4"}]}), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(cli_app, ["eval", str(suite), "--bootstrap", "eval_fail_bootstrap:app"])
    assert result.exit_code == 1
    assert "0/1 passed" in result.output
