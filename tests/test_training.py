from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agentkit.cli import app as cli_app
from agentkit.db.repositories import Repositories
from agentkit.migrate import migrate_openclaw
from agentkit.session import serialize_message
from agentkit.trajectory import (
    compress_content,
    compress_messages,
    export_trajectory,
    iter_trajectories,
    render_jsonl,
)


def _conversation() -> list:
    return [
        ModelRequest(parts=[UserPromptPart("total the file")]),
        ModelResponse(
            parts=[
                ToolCallPart(tool_name="run_code", args={"code": "sum()"}, tool_call_id="c1"),
            ]
        ),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="run_code", content="x" * 2000, tool_call_id="c1")]
        ),
        ModelResponse(parts=[TextPart("The total is 42.")]),
    ]


def test_export_trajectory_normalizes_steps():
    trajectory = export_trajectory(_conversation())
    assert [step["role"] for step in trajectory["steps"]] == [
        "user",
        "tool_call",
        "tool_result",
        "assistant",
    ]
    assert trajectory["steps"][1]["tool"] == "run_code"
    assert trajectory["count"] == 4


def test_export_trajectory_compresses_tool_results():
    trajectory = export_trajectory(_conversation(), compress=True, max_chars=100)
    tool_result = trajectory["steps"][2]
    assert "elided" in tool_result["content"]
    assert len(tool_result["content"]) < 2000


def test_compress_content_keeps_head_and_tail():
    compressed = compress_content("a" * 1000, max_chars=100)
    assert compressed.startswith("a") and compressed.endswith("a")
    assert "elided" in compressed
    assert compress_content("short") == "short"


def test_compress_messages_roundtrips():
    payloads = [serialize_message(m) for m in _conversation()]
    compressed = compress_messages(payloads, max_chars=100)
    assert any("elided" in json.dumps(part) for part in compressed)
    assert len(compressed) == len(payloads)


def test_render_jsonl_is_one_object_per_line():
    text = render_jsonl([{"a": 1}, {"b": 2}])
    assert len(text.splitlines()) == 2
    assert json.loads(text.splitlines()[0]) == {"a": 1}


def test_read_prompts_handles_text_and_jsonl(tmp_path: Path):
    from agentkit.cli.commands.training import _read_prompts

    path = tmp_path / "prompts.jsonl"
    path.write_text(
        'plain line\n{"prompt": "json prompt"}\n{"text": "alt"}\n\nnot json {oops\n',
        encoding="utf-8",
    )
    assert _read_prompts(path) == ["plain line", "json prompt", "alt", "not json {oops"]


def test_generate_batch_writes_jsonl(tmp_path: Path, monkeypatch):
    module = tmp_path / "gen_bootstrap.py"
    module.write_text(
        "from agentkit import App\n"
        "from agentkit.foundation.agent import Agent\n"
        "from pydantic_ai.messages import ModelResponse, TextPart\n"
        "from pydantic_ai.models.function import FunctionModel\n"
        "app = App('gen', discover=False)\n"
        "app.agent(Agent.make('gen').instructions('x').output(str))\n"
        "app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart('out')]))\n",
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts.txt"
    prompts.write_text("one\ntwo\n", encoding="utf-8")
    out = tmp_path / "generations.jsonl"
    monkeypatch.syspath_prepend(str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "generate",
            str(prompts),
            "--out",
            str(out),
            "--bootstrap",
            "gen_bootstrap:app",
            "--n",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4  # 2 prompts x 2 samples
    first = json.loads(lines[0])
    assert first["prompt"] == "one"
    assert first["output"] == "out"


async def test_iter_trajectories_over_repos(repos: Repositories):
    await repos.conversations.get_or_create("cli:t", channel="cli")
    await repos.messages.append("cli:t", [serialize_message(m) for m in _conversation()])
    items = [item async for item in iter_trajectories(repos)]
    assert items and items[0]["conversation_id"] == "cli:t"


def _openclaw_source(root: Path) -> Path:
    (root / "skills" / "notes").mkdir(parents=True)
    (root / "skills" / "notes" / "SKILL.md").write_text("# Notes\n", encoding="utf-8")
    (root / "config.json").write_text('{"name": "claw"}', encoding="utf-8")
    (root / "memories.jsonl").write_text(
        '{"content": "My name is Ada"}\nplain memory\n', encoding="utf-8"
    )
    (root / "schedules.json").write_text('[{"name": "daily"}]', encoding="utf-8")
    (root / "channels.json").write_text('{"telegram": true}', encoding="utf-8")
    return root


def test_migrate_openclaw_imports(tmp_path: Path):
    source = _openclaw_source(tmp_path / "claw")
    target = tmp_path / "home"
    report = migrate_openclaw(source, target=target)
    assert report.config and report.memories == 2 and report.skills == 1
    assert (target / "import" / "memories.jsonl").is_file()
    assert (target / "skills" / "notes" / "SKILL.md").is_file()
    assert report.schedules == 1 and report.channels == 1


def test_migrate_openclaw_dry_run_writes_nothing(tmp_path: Path):
    source = _openclaw_source(tmp_path / "claw")
    target = tmp_path / "home"
    report = migrate_openclaw(source, target=target, dry_run=True)
    assert report.memories == 2
    assert not (target / "import").exists()


def test_migrate_cli(tmp_path: Path):
    source = _openclaw_source(tmp_path / "claw")
    runner = CliRunner()
    result = runner.invoke(
        cli_app, ["migrate", "openclaw", str(source), "--target", str(tmp_path / "home")]
    )
    assert result.exit_code == 0, result.stdout
    assert "memories: 2" in result.stdout
