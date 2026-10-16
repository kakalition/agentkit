"""Eval graders — score a case output (or a stored run trace).

Reference graders (``exact``, ``contains``, ``schema``, ``trace``) are synchronous;
the ``llm_judge`` grader is async (it calls a model). :func:`run_grader` awaits a
grader whether it returned a value or an awaitable.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from agentkit.contracts.eval_dataset import Grader, GradeResult
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, EvalGraderDriver
from agentkit.support.manager import Manager

__all__ = [
    "ContainsGrader",
    "ExactMatchGrader",
    "GRADERS",
    "Grader",
    "LLMJudgeGrader",
    "SchemaGrader",
    "TraceGrader",
    "run_grader",
]

#: Named custom graders (``register_grader``); reference ones live in the manager.
GRADERS: dict[str, Grader] = {}


def register_grader(name: str, grader: Grader) -> Grader:
    GRADERS[str(name)] = grader
    return grader


def _expect(case: Any) -> str | None:
    value = getattr(case, "expect", None)
    if value is None and isinstance(case, dict):
        value = case.get("expect")
    return None if value is None else str(value)


def _output_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    value = getattr(output, "output", None)
    return value if isinstance(value, str) else str(output)


class ExactMatchGrader:
    """Pass when the output equals the case's expected text."""

    name = "exact"

    def grade(self, case: Any, output: Any) -> GradeResult:
        expected = _expect(case)
        text = _output_text(output).strip()
        if expected is None:
            return GradeResult(False, 0.0, "case has no expectation")
        ok = text == expected.strip()
        return GradeResult(ok, 1.0 if ok else 0.0, "" if ok else f"expected {expected!r}")


class ContainsGrader:
    """Pass when the output contains every expected substring."""

    name = "contains"

    def grade(self, case: Any, output: Any) -> GradeResult:
        needles = getattr(case, "contains", None) or _expect(case)
        if needles is None:
            return GradeResult(False, 0.0, "case has no expectation")
        needles = [needles] if isinstance(needles, str) else list(needles)
        text = _output_text(output)
        missing = [needle for needle in needles if str(needle) not in text]
        return GradeResult(
            not missing, 0.0 if missing else 1.0, f"missing {missing}" if missing else ""
        )


class SchemaGrader:
    """Pass when the output is JSON satisfying the case's declared schema.

    ``case.metadata["schema"]`` (or ``case["schema"]``) is a mapping of required
    keys to JSON types; only those keys are checked.
    """

    name = "schema"

    def grade(self, case: Any, output: Any) -> GradeResult:
        schema = None
        if isinstance(case, dict):
            schema = case.get("schema") or (case.get("metadata") or {}).get("schema")
        else:
            schema = (getattr(case, "metadata", None) or {}).get("schema")
        text = _output_text(output)
        try:
            parsed = json.loads(text)
        except ValueError:
            return GradeResult(False, 0.0, "output is not JSON")
        if not schema:
            return GradeResult(True, 1.0, "no schema declared; JSON parsed")
        errors: list[str] = []
        for key, kind in schema.items():
            if key not in parsed:
                errors.append(f"missing key {key!r}")
                continue
            if not _json_type_matches(parsed[key], kind):
                errors.append(f"{key!r} is not {kind}")
        return GradeResult(not errors, 0.0 if errors else 1.0, "; ".join(errors))


class TraceGrader:
    """Pass when a stored run trace matches declared tools and has no errors.

    The case may declare ``calls`` (tools that must appear) and ``not_calls``.
    ``output`` is either a list of :class:`~agentkit.runs.RunEvent` or of dicts.
    """

    name = "trace"

    def grade(self, case: Any, output: Any) -> GradeResult:
        events = list(output or [])
        tools = {
            getattr(event, "tool", "") or (event.get("tool", "") if isinstance(event, dict) else "")
            for event in events
        }
        tools.discard("")
        kinds = {
            getattr(event, "kind", "") or (event.get("kind", "") if isinstance(event, dict) else "")
            for event in events
        }
        required = getattr(case, "calls", None)
        required = [required] if isinstance(required, str) else list(required or [])
        missing = [tool for tool in required if tool not in tools]
        if "error" in kinds:
            return GradeResult(False, 0.0, "run recorded an error")
        return GradeResult(not missing, 0.0 if missing else 1.0, f"missing {missing}" if missing else "")


class LLMJudgeGrader:
    """Grade an output against free-text criteria with a model (async)."""

    name = "llm_judge"

    def __init__(self, model: Any = None, *, criteria: str = "", threshold: float = 0.5) -> None:
        self.model = model
        self.criteria = criteria
        self.threshold = threshold

    def grade(self, case: Any, output: Any) -> Any:
        return self._grade_async(case, output)

    async def _grade_async(self, case: Any, output: Any) -> GradeResult:
        criteria = self.criteria or (
            isinstance(case, dict) and case.get("criteria") or getattr(case, "criteria", "")
        )
        if not criteria:
            return GradeResult(False, 0.0, "no criteria provided")
        try:
            from pydantic_ai import Agent as PydanticAgent

            agent = PydanticAgent(self.model, output_type=float, instructions=criteria)
            result = await agent.run(f"Criteria: {criteria}\n\nOutput:\n{_output_text(output)}")
            score = float(getattr(result, "output", 0.0) or 0.0)
        except Exception as exc:  # pragma: no cover - model/extra dependent
            return GradeResult(False, 0.0, f"judge failed: {exc}")
        return GradeResult(score >= self.threshold, score, f"score {score:.2f}")


async def run_grader(grader: Any, case: Any, output: Any) -> GradeResult:
    """Run a grader (sync or async) and normalise the result to a ``GradeResult``."""
    result = grader.grade(case, output)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, GradeResult):
        return result
    if isinstance(result, bool):
        return GradeResult(result)
    if isinstance(result, (int, float)):
        return GradeResult(float(result) >= 0.5, float(result))
    if isinstance(result, str):
        return GradeResult(False, 0.0, result)
    return GradeResult(bool(result))


def _json_type_matches(value: Any, kind: Any) -> bool:
    mapping: dict[str, Any] = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    if kind in mapping:
        expected = mapping[kind]
        return isinstance(value, expected) and not (
            kind in {"number", "integer"} and isinstance(value, bool)
        )
    return True


class EvalGraderManager(Manager):
    """Resolves the configured grader (``eval_grader_driver``)."""

    kind = DriverKind.EVAL_GRADER
    default_driver = EvalGraderDriver.EXACT

    def create_exact_driver(self, app: Any) -> ExactMatchGrader:
        return ExactMatchGrader()

    def create_contains_driver(self, app: Any) -> ContainsGrader:
        return ContainsGrader()

    def create_schema_driver(self, app: Any) -> SchemaGrader:
        return SchemaGrader()

    def create_llm_judge_driver(self, app: Any) -> LLMJudgeGrader:
        return LLMJudgeGrader(getattr(app, "_model", None))

    def create_trace_driver(self, app: Any) -> TraceGrader:
        return TraceGrader()


def grader_by_name(name: str) -> Any:
    """Resolve a grader by driver name or a registered custom name (or ``None``)."""
    if name in GRADERS:
        return GRADERS[name]
    builders = {
        "exact": ExactMatchGrader,
        "contains": ContainsGrader,
        "schema": SchemaGrader,
        "trace": TraceGrader,
        "llm_judge": LLMJudgeGrader,
    }
    factory = builders.get(name)
    return factory() if factory is not None else None


@register_driver(DriverKind.EVAL_GRADER, EvalGraderDriver.EXACT)
def _exact_grader_driver(app: Any) -> ExactMatchGrader:
    return ExactMatchGrader()


@register_driver(DriverKind.EVAL_GRADER, EvalGraderDriver.CONTAINS)
def _contains_grader_driver(app: Any) -> ContainsGrader:
    return ContainsGrader()


@register_driver(DriverKind.EVAL_GRADER, EvalGraderDriver.SCHEMA)
def _schema_grader_driver(app: Any) -> SchemaGrader:
    return SchemaGrader()


@register_driver(DriverKind.EVAL_GRADER, EvalGraderDriver.LLM_JUDGE)
def _llm_judge_grader_driver(app: Any) -> LLMJudgeGrader:
    return LLMJudgeGrader(getattr(app, "_model", None))
