from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from typer.testing import CliRunner

from agentkit import Agent
from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.db.repositories import Repositories
from agentkit.deps import Deps
from agentkit.learning import (
    LESSON_TASK,
    attach_learning,
    lessons_digest,
    reflect,
    register_reflect_task,
)
from agentkit.runtime import build_runtime, repositories
from agentkit.session import serialize_message


async def _seed(repos: Repositories, texts: list[str], conversation_id: str = "conv1") -> None:
    await repos.conversations.get_or_create(conversation_id)
    payloads = [
        serialize_message(ModelRequest(parts=[UserPromptPart(content=text)])) for text in texts
    ]
    await repos.messages.append(conversation_id, payloads)


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


async def test_reflect_extracts_lessons_preferences_facts(repos: Repositories):
    await _seed(
        repos,
        ["I prefer metric units.", "Always refill the water bowl each morning.", "My name is Ada."],
    )
    summary = await reflect(repos)

    assert summary["skipped"] is False
    assert summary["lessons"] >= 1
    assert summary["preferences"] >= 1
    assert summary["facts"] >= 1

    lessons = await repos.memories.list(kind="procedural")
    assert any("water bowl" in row.content for row in lessons)
    assert await repos.learning_runs.latest("conv1") is not None
    profile = await repos.profile.get()
    assert profile is not None and "metric units" in (profile.preferences or "")


async def test_reflect_dry_run_changes_nothing(repos: Repositories):
    await _seed(repos, ["Always refill the water bowl each morning."])
    summary = await reflect(repos, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["lessons"] >= 1
    assert await repos.memories.list(kind="procedural") == []
    assert await repos.learning_runs.latest("conv1") is None


async def test_reflect_uses_model_extraction(repos: Repositories):
    await _seed(repos, ["some offline-irrelevant chatter"])
    payload = {"lessons": ["when tired, rest"], "facts": ["the project uses postgres"]}
    model = FunctionModel(
        lambda messages, info: ModelResponse(parts=[TextPart(json.dumps(payload))])
    )

    summary = await reflect(repos, model=model)

    assert summary["lessons"] == 1
    assert summary["facts"] == 1
    assert any(row.content == "when tired, rest" for row in await repos.memories.list(kind="procedural"))


async def test_reflect_model_falls_back_on_bad_json(repos: Repositories):
    await _seed(repos, ["Always refill the water bowl each morning."])
    model = FunctionModel(
        lambda messages, info: ModelResponse(parts=[TextPart("not valid json")])
    )

    summary = await reflect(repos, model=model)

    assert summary["lessons"] >= 1


# ---------------------------------------------------------------------------
# Idempotency + dedupe + redaction
# ---------------------------------------------------------------------------


async def test_reflect_is_idempotent_per_window(repos: Repositories):
    await _seed(repos, ["Always refill the water bowl each morning."])

    first = await reflect(repos)
    assert first["skipped"] is False

    again = await reflect(repos)
    assert again["skipped"] is True

    other = await reflect(repos, window=1)
    assert other["skipped"] is False


async def test_reflect_dedupes_near_identical_lessons(repos: Repositories):
    await repos.memories.add(
        "Always refill the water bowl each morning.", kind="procedural", importance=0.9
    )
    await _seed(repos, ["Always refill the water bowl each morning."])

    summary = await reflect(repos)

    assert summary["merged"] >= 1
    assert len(await repos.memories.list(kind="procedural")) == 1


async def test_reflect_redacts_pii(repos: Repositories):
    await _seed(repos, ["Always email me at ada@example.com when you are done."])

    await reflect(repos)

    rows = await repos.memories.list(kind="procedural")
    assert rows
    assert "ada@example.com" not in rows[0].content
    assert "[redacted:email]" in rows[0].content


# ---------------------------------------------------------------------------
# Skill distillation
# ---------------------------------------------------------------------------


async def test_reflect_reports_skill_candidates(tmp_path: Path, repos: Repositories, deps: Deps):
    deps.settings.learning_skill_threshold = 2
    await repos.memories.add(
        "Always refill the water bowl each morning.", kind="procedural", importance=0.9
    )
    await _seed(repos, ["Always refill the water bowl each morning."])

    summary = await reflect(repos, settings=deps.settings)

    assert summary["skill_candidates"]
    assert summary["skills"] == []


async def test_reflect_writes_skill_when_auto_skills(
    tmp_path: Path, repos: Repositories, deps: Deps
):
    deps.settings.skills_dir = str(tmp_path / "skills")
    deps.settings.learning_skill_threshold = 2
    await repos.memories.add(
        "Always refill the water bowl each morning.", kind="procedural", importance=0.9
    )
    await _seed(repos, ["Always refill the water bowl each morning."])

    summary = await reflect(repos, settings=deps.settings, auto_skills=True)

    assert summary["skills"]
    assert list((tmp_path / "skills").glob("*/SKILL.md"))


# ---------------------------------------------------------------------------
# Digest + instructions
# ---------------------------------------------------------------------------


async def test_lessons_digest(repos: Repositories):
    assert await lessons_digest(repos) is None
    row = await repos.memories.add("Always water the plants.", kind="procedural")
    digest = await lessons_digest(repos)
    assert digest is not None
    assert f"#{row.id} Always water the plants." in digest


async def test_learning_digest_is_injected_into_instructions(repos: Repositories, deps: Deps):
    row = await repos.memories.add("Always water the plants.", kind="procedural")
    agent = Agent.make("l").instructions("x").learning().output(str).build()
    captured: dict[str, str | None] = {}

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        captured["instructions"] = info.instructions
        return ModelResponse(parts=[TextPart("ok")])

    await agent.run("hi", deps=deps, model=FunctionModel(model_fn))

    instructions = captured["instructions"] or ""
    assert "Always water the plants." in instructions
    assert f"#{row.id}" in instructions


# ---------------------------------------------------------------------------
# Tools + gating
# ---------------------------------------------------------------------------


def test_attach_learning_registers_tools_and_is_idempotent():
    agent: PydanticAgent[Deps, str] = PydanticAgent(
        name="l", deps_type=Deps, output_type=str, instructions="x"
    )
    attach_learning(agent)
    attach_learning(agent)
    tools = set(agent._function_toolset.tools.keys())
    assert {"learn", "reflect", "list_lessons", "forget_lesson"} <= tools


async def test_learning_tools_roundtrip(deps: Deps):
    agent = Agent.make("l").instructions("x").learning().output(str).build()
    ctx = _ctx(deps)

    assert "learned as #" in await _fn(agent, "learn")(ctx, "Always be kind to cats.")
    listing = await _fn(agent, "list_lessons")(ctx)
    assert "cats" in listing

    lesson_id = int(listing.split("#")[1].split(" ")[0])
    assert await _fn(agent, "forget_lesson")(ctx, lesson_id) == "forgotten"
    assert await _fn(agent, "forget_lesson")(ctx, lesson_id) == "no such lesson"


async def test_learn_tool_redacts(deps: Deps):
    agent = Agent.make("l").instructions("x").learning().output(str).build()
    await _fn(agent, "learn")(_ctx(deps), "Always email bob@secret.com")

    rows = await deps.repos.memories.list(kind="procedural")
    assert rows
    assert "bob@secret.com" not in rows[0].content


def test_full_learning_disabled_skips_tools(tmp_path: Path):
    settings = AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash", learning_enabled=False)
    agent = (
        Agent.make("l").instructions("x").full(settings=settings).output(str).build(settings=settings)
    )
    tools = set(agent._function_toolset.tools.keys())
    assert not ({"learn", "reflect", "list_lessons", "forget_lesson"} & tools)


def test_register_reflect_task_is_idempotent():
    assert register_reflect_task() == LESSON_TASK
    assert register_reflect_task() == LESSON_TASK
    from agentkit.scheduler import TASKS

    assert LESSON_TASK in TASKS


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _seed_cli(tmp_path: Path) -> None:
    runtime = build_runtime()

    async def _run() -> None:
        async with repositories(runtime) as repos:
            await _seed(repos, ["Always refill the water bowl each morning."], "cli:default")

    asyncio.run(_run())


def test_cli_learning_reflect_lessons_forget(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    monkeypatch.setenv("WEBUI_ENABLED", "false")
    get_settings.cache_clear()
    _seed_cli(tmp_path)
    runner = CliRunner()

    dry = runner.invoke(cli_app, ["learning:reflect", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "would learn" in dry.output

    reflected = runner.invoke(cli_app, ["learning:reflect"])
    assert reflected.exit_code == 0, reflected.output
    assert "learned" in reflected.output

    lessons = runner.invoke(cli_app, ["learning:lessons"])
    assert lessons.exit_code == 0, lessons.output
    assert "water bowl" in lessons.output

    lesson_id = lessons.output.split("#")[1].split(" ")[0]
    forgotten = runner.invoke(cli_app, ["learning:forget", lesson_id])
    assert forgotten.exit_code == 0, forgotten.output
    assert f"forgotten #{lesson_id}" in forgotten.output

    missing = runner.invoke(cli_app, ["learning:forget", lesson_id])
    assert missing.exit_code == 1

    get_settings.cache_clear()
