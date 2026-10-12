from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App, Budget, Prompt, PromptRegistry
from agentkit.errors import BudgetExceeded
from agentkit.limits import check_budget
from agentkit.runtime import Runtime


def _app(runtime: Runtime, model) -> App:  # noqa: ANN001
    app = App(name="ops", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    app.agent(Agent.make("ops").instructions("x").output(str))
    return app


def test_prompt_registry_discovers_versions(tmp_path: Path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "greeting.md").write_text(
        "---\nname: greeting\nversion: 1\n---\nHi {name}, welcome.", encoding="utf-8"
    )
    (prompts / "greeting_v2.md").write_text(
        "---\nname: greeting\nversion: 2\n---\nHello {name}!", encoding="utf-8"
    )
    registry = PromptRegistry([prompts]).discover()
    assert registry.get("greeting").version == 2
    assert registry.render("greeting", name="Ada") == "Hello Ada!"


def test_builder_prompt_from_file(tmp_path: Path):
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("---\nversion: 1\n---\nBe {style}.", encoding="utf-8")
    agent = Agent.make("p").instructions("base").prompt(prompt_file, style="concise").output(str).build()
    assert agent is not None


def test_prompt_dataclass_render():
    assert Prompt("x", "Hello {who}").render(who="world") == "Hello world"


def test_budget_violations_and_check(runtime: Runtime):
    app = _app(runtime, None)
    app.boot()
    with app.repositories() as repos:
        repos.usage.add(conversation_id="cli:1", requests=3, total_tokens=100, cost_usd=0.5)
        with pytest.raises(BudgetExceeded):
            check_budget(repos, Budget(max_requests=1))
        totals = check_budget(repos, Budget(max_requests=10, max_tokens=1000, max_cost=5.0))
        assert totals["requests"] == 3


async def test_app_budget_blocks_run(runtime: Runtime):
    app = _app(runtime, FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])))
    app.budget(Budget(max_requests=0))
    app.boot()
    with pytest.raises(BudgetExceeded):
        await app.run("hi")


async def test_fork_and_replay(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("reply")]))
    app = _app(runtime, model)
    app.boot()
    await app.run("first question", conversation_id="cli:main")
    copied = app.fork("cli:main", "cli:branch")
    assert copied >= 2

    replayed = await app.replay("cli:main", target="cli:replay")
    assert replayed.output == "reply"
    with app.repositories() as repos:
        assert repos.messages.list("cli:replay")
