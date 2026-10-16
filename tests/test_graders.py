from __future__ import annotations

from agentkit.evals import Case
from agentkit.graders import (
    ContainsGrader,
    ExactMatchGrader,
    LLMJudgeGrader,
    SchemaGrader,
    TraceGrader,
    grader_by_name,
    register_grader,
    run_grader,
)


async def test_exact_and_contains_graders():
    case = Case(name="c", input="2+2", expect="4")
    assert (await run_grader(ExactMatchGrader(), case, "4")).passed
    assert not (await run_grader(ExactMatchGrader(), case, "5")).passed
    assert (await run_grader(ContainsGrader(), case, "answer: 4!")).passed


def test_schema_grader():
    case = Case(name="c", input="i", metadata={"schema": {"a": "integer"}})
    assert SchemaGrader().grade(case, '{"a": 1}').passed
    assert not SchemaGrader().grade(case, '{"a": "x"}').passed
    assert not SchemaGrader().grade(case, "not json").passed


def test_trace_grader_flags_errors_and_missing_tools():
    case = Case(name="c", input="i", calls="search")
    assert TraceGrader().grade(case, [{"kind": "tool", "tool": "search"}]).passed
    assert not TraceGrader().grade(case, [{"kind": "tool", "tool": "other"}]).passed
    assert not TraceGrader().grade(case, [{"kind": "error"}]).passed


async def test_llm_judge_missing_criteria_is_failure():
    result = await run_grader(LLMJudgeGrader(), Case(name="c", input="i"), "out")
    assert not result.passed
    assert "criteria" in result.reason


def test_grader_by_name_and_custom_registration():
    assert grader_by_name("exact").name == "exact"
    assert grader_by_name("nope") is None

    class Custom:
        name = "custom"

        def grade(self, case, output):
            return True

    register_grader("custom", Custom())
    assert grader_by_name("custom").name == "custom"
