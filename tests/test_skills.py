from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agentkit import Skill, SkillRegistry, load_skill_file, parse_front_matter
from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings
from agentkit.foundation.agent import Agent


def _write_skill(
    root: Path,
    name: str,
    description: str,
    *,
    body: str = "Do the thing.",
    front_matter: bool = True,
    files: dict[str, str] | None = None,
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    header = f"---\nname: {name}\ndescription: {description}\n---\n" if front_matter else ""
    (directory / "SKILL.md").write_text(f"{header}# {name}\n\n{body}\n", encoding="utf-8")
    for relative, content in (files or {}).items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return directory


def test_parse_front_matter_scalars_and_lists():
    meta, body = parse_front_matter(
        "---\nname: pdf\ndescription: \"Extract: text\"\nallowed-tools: [read_file, run]\n---\nBody here\n"
    )
    assert meta["name"] == "pdf"
    assert meta["description"] == "Extract: text"
    assert meta["allowed-tools"] == ["read_file", "run"]
    assert body == "Body here"


def test_parse_front_matter_without_fence():
    meta, body = parse_front_matter("Just a body\n")
    assert meta == {}
    assert body == "Just a body"


def test_registry_discover_get_index_and_load(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "Extract text from PDFs", files={"references/style.md": "style"})
    _write_skill(tmp_path, "csv", "Summarize tables")

    registry = SkillRegistry.from_paths([tmp_path]).discover()
    assert set(registry.names()) == {"pdf", "csv"}
    assert len(registry) == 2
    assert "pdf" in registry
    assert registry.get("pdf").description == "Extract text from PDFs"
    index = registry.index()
    assert "- pdf: Extract text from PDFs" in index
    assert "load_skill" in index

    loaded = registry.load("pdf")
    assert "# Skill: pdf" in loaded
    assert "references/style.md" in loaded
    assert registry.load("missing").startswith("No skill named")

    assert registry.read_file("pdf", "references/style.md") == "style"


def test_skill_read_refuses_path_traversal(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "desc")
    skill = load_skill_file(tmp_path / "pdf" / "SKILL.md")
    with pytest.raises(ValueError):
        skill.read("../../etc/passwd")
    assert skill.files() == []


def test_registry_from_settings_uses_skills_dir(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "notes", "Take notes")
    settings = AgentSettings(agent_home=tmp_path, skills_dir=str(root))
    registry = SkillRegistry.from_settings(settings).discover()
    assert registry.names() == ["notes"]


def test_registry_tolerates_missing_roots(tmp_path: Path):
    registry = SkillRegistry.from_paths([tmp_path / "nope"]).discover()
    assert len(registry) == 0
    assert registry.index() == ""


def test_registry_skips_malformed_skill(tmp_path: Path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "SKILL.md").write_bytes(b"\xff\xfe not utf-8")
    _write_skill(tmp_path, "good", "Fine")
    registry = SkillRegistry.from_paths([tmp_path]).discover()
    assert registry.names() == ["good"]


def test_skill_allowed_tools(tmp_path: Path):
    directory = tmp_path / "tooly"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: tooly\ndescription: d\nallowed-tools:\n  - read\n  - write\n---\nbody\n",
        encoding="utf-8",
    )
    skill = load_skill_file(directory / "SKILL.md")
    assert skill.allowed_tools == ["read", "write"]


def _tool_return(messages: list[ModelMessage]) -> str | None:
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart):
                return str(part.content)
    return None


async def test_builder_skills_attach_tools_and_instructions(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "Extract text from PDFs", body="Use the extractor.")
    registry = SkillRegistry.from_paths([tmp_path]).discover()

    captured: dict[str, object] = {}

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.setdefault("instructions", info.instructions)
        returned = _tool_return(messages)
        if returned is not None:
            return ModelResponse(parts=[TextPart(returned)])
        return ModelResponse(parts=[ToolCallPart("load_skill", {"name": "pdf"})])

    agent = (
        Agent.make("skillful").instructions("base").skills(registry).output(str).build()
    )
    tools = set(agent._function_toolset.tools.keys())
    assert {"list_skills", "load_skill", "read_skill_file"} <= tools

    result = await agent.run("help", model=FunctionModel(model_fn))
    assert "Use the extractor." in result.output
    assert "Extract text from PDFs" in str(captured["instructions"])


def test_builder_skills_disabled_when_settings_off(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "pdf", "Extract")
    settings = AgentSettings(agent_home=tmp_path, skills_dir=str(root), skills_enabled=False)
    agent = Agent.make("x").instructions("i").skills().output(str).build(settings=settings)
    tools = set(agent._function_toolset.tools.keys())
    assert "load_skill" not in tools


def test_builder_skills_from_paths(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "Extract")
    agent = Agent.make("x").instructions("i").skills(paths=[tmp_path]).output(str).build()
    assert "load_skill" in set(agent._function_toolset.tools.keys())


def test_cli_skills_list_and_show(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "Extract text from PDFs", body="Use the extractor.")
    runner = CliRunner()

    listed = runner.invoke(cli_app, ["skills", "list", "--path", str(tmp_path)])
    assert listed.exit_code == 0, listed.output
    assert "pdf" in listed.output

    shown = runner.invoke(cli_app, ["skills", "show", "pdf", "--path", str(tmp_path)])
    assert shown.exit_code == 0
    assert "Use the extractor." in shown.output

    missing = runner.invoke(cli_app, ["skills", "show", "nope", "--path", str(tmp_path)])
    assert missing.exit_code == 1


def test_skill_dataclass_render():
    skill = Skill(name="s", path=Path("."), description="d", body="b")
    assert "# Skill: s" in skill.render()


def test_skill_registry_tool_policy():
    from agentkit.policy import ToolPolicy

    empty = SkillRegistry.from_paths([]).discover()
    assert empty.tool_policy().allow is None

    root_registry = SkillRegistry(
        skills=[
            Skill(name="a", path=Path("."), metadata={"allowed-tools": ["read_skill_file"]}),
            Skill(name="b", path=Path("."), metadata={"allowed-tools": "run"}),
        ]
    )
    policy = root_registry.tool_policy(extra=["load_skill"])
    assert isinstance(policy, ToolPolicy)
    assert policy.allow == {"read_skill_file", "run", "load_skill"}


def test_builder_skills_enforce_builds(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "Extract")
    registry = SkillRegistry.from_paths([tmp_path]).discover()
    agent = (
        Agent.make("x")
        .instructions("i")
        .skills(registry, enforce=True)
        .output(str)
        .build()
    )
    assert "load_skill" in set(agent._function_toolset.tools.keys())


def test_front_matter_yaml_block_list_and_quoting():
    meta, body = parse_front_matter(
        "---\nname: x\ndescription: 'has: colon'\nitems:\n  - a\n  - b\nempty: []\n"
        "numbers: [1, 2]\n---\nBody\n"
    )
    assert meta["name"] == "x"
    assert meta["description"] == "has: colon"
    assert meta["items"] == ["a", "b"]
    assert meta["empty"] == []
    assert meta["numbers"] == [1, 2]
    assert body == "Body"


def test_front_matter_empty_is_blank_mapping():
    meta, body = parse_front_matter("---\n---\nBody\n")
    assert meta == {}
    assert body == "Body"


def test_front_matter_malformed_raises():
    import pytest

    with pytest.raises(ValueError, match="front matter"):
        parse_front_matter("---\nname: [unterminated\n---\nBody\n")
    with pytest.raises(ValueError, match="mapping"):
        parse_front_matter("---\n- a\n- b\n---\nBody\n")


def test_skill_allowed_tools_string_form(tmp_path: Path):
    directory = tmp_path / "one"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: one\ndescription: d\nallowed-tools: read\n---\nbody\n", encoding="utf-8"
    )
    assert load_skill_file(directory / "SKILL.md").allowed_tools == ["read"]


def test_registry_discovers_root_level_skill(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text(
        "---\nname: root\ndescription: root skill\n---\nbody\n", encoding="utf-8"
    )
    registry = SkillRegistry.from_paths([tmp_path]).discover()
    assert registry.names() == ["root"]


def test_skill_read_bundled_and_missing(tmp_path: Path):
    _write_skill(tmp_path, "pdf", "d", files={"a.txt": "hello"})
    registry = SkillRegistry.from_paths([tmp_path]).discover()
    assert registry.read_file("pdf", "a.txt") == "hello"
    assert registry.read_file("pdf", "missing.txt").startswith("Could not read")
    assert registry.read_file("nope", "a.txt").startswith("No skill named")
