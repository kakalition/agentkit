from __future__ import annotations

import json

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App
from agentkit.deps import Deps
from agentkit.evals import Case, EvalSuite
from agentkit.runtime import Runtime
from agentkit.session import ChatResult


def _result(output: str, tool_calls: list[str] | None = None) -> ChatResult:
    return ChatResult(output=output, tool_calls=tool_calls or [])


def test_case_assertions():
    passing = Case("ok", input="?", expect="4", contains="4", not_contains="5", regex=r"\d")
    assert passing.evaluate(_result("4")) == []

    failing = Case("bad", input="?", expect="4", contains=["4", "x"], not_contains="no", calls="tool")
    failures = failing.evaluate(_result("no", ["other"]))
    assert any("expected" in f for f in failures)
    assert any("missing" in f for f in failures)
    assert any("should not contain" in f for f in failures)
    assert any("was not called" in f for f in failures)


def test_case_custom_check():
    case = Case("custom", input="?", check=lambda result: "needs 4" if result.output != "4" else True)
    assert case.evaluate(_result("4")) == []
    assert case.evaluate(_result("3")) == ["needs 4"]


async def test_suite_runs_against_app(runtime: Runtime):
    model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("4")]))
    app = App(name="evals", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    app.agent(Agent.make("evals").instructions("x").output(str))
    app.boot()

    suite = EvalSuite(
        [Case("math", input="2+2?", expect="4"), Case("wrong", input="2+2?", expect="5")],
        name="smoke",
    )
    report = await suite.run(app)
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert not report.passed
    assert "smoke: 1/2 passed" in report.summary()
    with pytest.raises(AssertionError):
        report.raise_for_failures()


async def test_suite_runs_callable_target():
    async def target(text: str, conversation_id: str) -> ChatResult:
        return _result(text.upper())

    report = await EvalSuite([Case("upper", input="hi", expect="HI")]).run(target)
    assert report.passed


def test_suite_from_json_and_yaml(tmp_path):
    data = {"name": "loaded", "cases": [{"name": "a", "input": "x", "expect": "y"}]}
    json_path = tmp_path / "suite.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    suite = EvalSuite.from_file(json_path)
    assert suite.name == "loaded"
    assert suite.cases[0].name == "a"

    yaml_path = tmp_path / "suite.yaml"
    yaml_path.write_text(
        "name: ysuite\ncases:\n  - name: b\n    input: q\n    calls: search\n", encoding="utf-8"
    )
    ysuite = EvalSuite.from_file(yaml_path)
    assert ysuite.name == "ysuite"
    assert ysuite.cases[0].calls == "search"


async def test_suite_checks_tool_calls(runtime: Runtime):
    def model_fn(messages, info):  # noqa: ANN001
        has_return = any(
            isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", [])
        )
        if has_return:
            return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart("lookup", {"q": "x"})])

    async def lookup(ctx: RunContext[Deps], q: str) -> str:
        """Look something up."""
        return "found"

    app = App(name="tools", settings=runtime.settings, discover=False, model=FunctionModel(model_fn))
    app._runtime = runtime
    app.agent(Agent.make("tools").instructions("x").tool(lookup).output(str))
    app.boot()

    report = await EvalSuite([Case("uses lookup", input="find x", calls="lookup")]).run(app)
    assert report.passed
