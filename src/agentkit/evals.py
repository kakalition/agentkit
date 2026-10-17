"""Evaluations, run by Pydantic's official ``pydantic_evals`` framework.

agentkit keeps a small, ergonomic case/assertion API and delegates execution,
concurrency, retries, and reporting to :mod:`pydantic_evals`::

    from agentkit.evals import Case, EvalSuite

    suite = EvalSuite([
        Case("adds", input="what is 2+2?", expect="4"),
        Case("uses the calendar tool", input="book a slot", calls="create_event"),
        Case("stays in persona", input="hi", not_contains=["As an AI language model"]),
    ])
    report = await suite.run(app)
    report.raise_for_failures()

Suites load from YAML/JSON with :meth:`EvalSuite.from_file`; run from the CLI with
``agentkit eval suite.yaml``.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pydantic_evals
from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.reporting import EvaluationReport

from agentkit.contracts.evals import Reporter
from agentkit.session import ChatResult
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, EvalsReporterDriver
from agentkit.support.manager import Manager

__all__ = [
    "Case",
    "CaseResult",
    "EvalReporterManager",
    "EvalSuite",
    "JsonReporter",
    "PydanticReporter",
    "Report",
    "Reporter",
    "TextReporter",
    "assert_trajectory",
    "capture_turns",
    "load_captured",
]


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


_CASE_KEYS = {
    "name",
    "input",
    "prompt",
    "expect",
    "contains",
    "not_contains",
    "regex",
    "calls",
    "not_calls",
    "conversation_id",
}


@dataclass
class Case:
    """One evaluation case and its assertions."""

    name: str
    input: str
    expect: str | None = None
    contains: str | list[str] | None = None
    not_contains: str | list[str] | None = None
    regex: str | None = None
    calls: str | list[str] | None = None
    not_calls: str | list[str] | None = None
    check: Callable[[ChatResult], Any] | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Case:
        return cls(
            name=str(data["name"]),
            input=str(data.get("input") or data.get("prompt") or ""),
            expect=data.get("expect"),
            contains=data.get("contains"),
            not_contains=data.get("not_contains"),
            regex=data.get("regex"),
            calls=data.get("calls"),
            not_calls=data.get("not_calls"),
            conversation_id=data.get("conversation_id"),
            metadata={k: v for k, v in data.items() if k not in _CASE_KEYS},
        )

    def evaluate(self, result: ChatResult) -> list[str]:
        failures: list[str] = []
        output = result.output or ""
        if self.expect is not None and output.strip() != str(self.expect).strip():
            failures.append(f"expected {self.expect!r}, got {output!r}")
        for needle in _as_list(self.contains):
            if needle not in output:
                failures.append(f"missing {needle!r}")
        for needle in _as_list(self.not_contains):
            if needle in output:
                failures.append(f"should not contain {needle!r}")
        if self.regex and not re.search(self.regex, output):
            failures.append(f"output did not match /{self.regex}/")
        called = set(result.tool_calls or [])
        for tool in _as_list(self.calls):
            if tool not in called:
                failures.append(f"tool {tool!r} was not called (called: {sorted(called)})")
        for tool in _as_list(self.not_calls):
            if tool in called:
                failures.append(f"tool {tool!r} should not have been called")
        if self.check is not None:
            outcome = self.check(result)
            if outcome is False:
                failures.append("custom check failed")
            elif isinstance(outcome, str):
                failures.append(outcome)
        return failures


class _CaseAssertions(Evaluator[Case, ChatResult, Any]):
    """Bridges a :class:`Case`'s assertions into a ``pydantic_evals`` evaluator."""

    def evaluate(self, ctx: EvaluatorContext[Case, ChatResult, Any]) -> bool:
        if not isinstance(ctx.output, ChatResult):
            return False
        return not ctx.inputs.evaluate(ctx.output)


@dataclass
class CaseResult:
    case: Case
    output: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)


@dataclass
class Report:
    name: str
    results: list[CaseResult]
    pydantic_report: EvaluationReport | None = None

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.results if not result.passed)

    def failures(self) -> list[CaseResult]:
        return [result for result in self.results if not result.passed]

    def summary(self) -> str:
        lines = [f"{self.name}: {self.passed_count}/{len(self.results)} passed"]
        for result in self.failures():
            lines.append(f"  ✗ {result.case.name}: " + "; ".join(result.failures))
        return "\n".join(lines)

    def render(self) -> str:
        """The rich ``pydantic_evals`` table, when available."""
        if self.pydantic_report is not None:
            return self.pydantic_report.render()
        return self.summary()

    def raise_for_failures(self) -> None:
        if not self.passed:
            raise AssertionError(self.summary())


def _message_text(message: Any, part_types: tuple[type, ...]) -> str:
    chunks: list[str] = []
    for part in getattr(message, "parts", []) or []:
        content = getattr(part, "content", None)
        if isinstance(part, part_types) and isinstance(content, str):
            chunks.append(content)
    return " ".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


async def capture_turns(
    repos: Any,
    *,
    conversation_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Turn recent conversation turns into stored eval cases (input → expected).

    Each user prompt paired with the following assistant reply becomes a
    regression case, persisted in the ``evals_capture`` table. Returns the cases.
    """
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    from agentkit.session import deserialize_messages

    if conversation_id is None:
        conversations = await repos.conversations.list(limit=1)
        conversation_id = conversations[0].id if conversations else None
    if conversation_id is None:
        return []
    payloads = await repos.messages.list(conversation_id, limit=max(2, limit * 2))
    messages = deserialize_messages(payloads)

    captured: list[dict[str, Any]] = []
    pending: str | None = None
    for message in messages:
        if isinstance(message, ModelRequest):
            prompt = _message_text(message, (UserPromptPart,))
            if prompt:
                pending = prompt
        elif isinstance(message, ModelResponse) and pending:
            output = _message_text(message, (TextPart,))
            if output:
                case = {
                    "name": f"capture:{conversation_id}:{len(captured)}",
                    "input": pending,
                    "expect": output,
                    "conversation_id": conversation_id,
                }
                captured.append(case)
                pending = None
    store = getattr(repos, "evals_capture", None)
    if store is not None:
        for case in captured:
            await store.add(conversation_id, json.dumps(case))
    return captured


async def load_captured(
    repos: Any, *, conversation_id: str | None = None, name: str = "captured"
) -> EvalSuite:
    """Build an :class:`EvalSuite` from previously captured cases."""
    store = getattr(repos, "evals_capture", None)
    rows = await store.list(conversation_id=conversation_id) if store is not None else []
    cases = [Case.from_dict(json.loads(row.case)) for row in rows]
    return EvalSuite(cases, name=name)


class EvalSuite:
    """A named collection of cases, executed by ``pydantic_evals``."""

    def __init__(self, cases: Iterable[Case], *, name: str = "evals") -> None:
        self.cases = list(cases)
        self.name = name

    @classmethod
    def from_cases(cls, *cases: Case, name: str = "evals") -> EvalSuite:
        return cls(cases, name=name)

    @classmethod
    def from_file(cls, path: str | Path, *, name: str | None = None) -> EvalSuite:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            import yaml

            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        raw = data.get("cases", data) if isinstance(data, dict) else data
        suite_name = name or (data.get("name") if isinstance(data, dict) else None) or path.stem
        return cls([Case.from_dict(item) for item in raw], name=suite_name)

    def to_dataset(self) -> Dataset[Case, ChatResult, Any]:
        """The equivalent ``pydantic_evals`` dataset (for power users)."""
        return Dataset(
            name=self.name,
            cases=[
                pydantic_evals.Case(
                    name=case.name,
                    inputs=case,
                    metadata=case.metadata,
                    evaluators=[_CaseAssertions()],
                )
                for case in self.cases
            ],
        )

    async def run(self, target: Any, *, model: Any = None) -> Report:
        """Run every case against ``target`` (an ``App`` or a run callable)."""
        dataset = self.to_dataset()
        by_name = {case.name: case for case in self.cases}

        async def task(case: Case) -> ChatResult:
            conversation_id = case.conversation_id or f"eval:{case.name}"
            return await self._invoke(target, case.input, conversation_id, model)

        raw = await dataset.evaluate(task, progress=False)
        return self._to_report(raw, by_name)

    def _to_report(self, raw: Any, by_name: dict[str, Case]) -> Report:
        results: list[CaseResult] = []
        for report_case in raw.cases:
            case = by_name.get(report_case.name)
            if case is None:  # pragma: no cover - defensive
                continue
            result = report_case.output
            if isinstance(result, ChatResult):
                failures = case.evaluate(result)
                output = result.output
                tool_calls = list(result.tool_calls or [])
            else:  # pragma: no cover - task contract violation
                failures = ["task did not return a ChatResult"]
                output = str(result)
                tool_calls = []
            results.append(
                CaseResult(
                    case=case,
                    output=output,
                    passed=not failures,
                    failures=failures,
                    tool_calls=tool_calls,
                )
            )
        names = {result.case.name for result in results}
        for failure in raw.failures:
            case = by_name.get(failure.name) or Case(name=str(failure.name), input="")
            if case.name in names:
                continue
            results.append(
                CaseResult(
                    case=case,
                    output="",
                    passed=False,
                    failures=[str(getattr(failure, "error_message", "task failed"))],
                )
            )
        return Report(name=self.name, results=results, pydantic_report=raw)

    async def _invoke(
        self, target: Any, text: str, conversation_id: str, model: Any
    ) -> ChatResult:
        if hasattr(target, "run") and inspect.iscoroutinefunction(target.run):
            return await target.run(text, conversation_id=conversation_id)
        if callable(target):
            outcome = target(text, conversation_id)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            return outcome
        raise TypeError(f"cannot run evals against {type(target)!r}")


# ---------------------------------------------------------------------------
# Reporters + trajectory assertions
# ---------------------------------------------------------------------------


class TextReporter:
    """The default reporter: a compact pass/fail summary."""

    def render(self, report: Report) -> str:
        return report.summary()


class JsonReporter:
    """Render a report as JSON (machine-readable CI output)."""

    def render(self, report: Report) -> str:
        return json.dumps(
            {
                "name": report.name,
                "passed": report.passed,
                "passed_count": report.passed_count,
                "failed_count": report.failed_count,
                "cases": [
                    {
                        "name": result.case.name,
                        "passed": result.passed,
                        "failures": result.failures,
                        "tool_calls": result.tool_calls,
                    }
                    for result in report.results
                ],
            },
            default=str,
        )


class PydanticReporter:
    """Use ``pydantic_evals``' own rich table renderer when available."""

    def render(self, report: Report) -> str:
        return report.render()


class EvalReporterManager(Manager):
    """Resolves the configured eval reporter (``evals_reporter_driver``, default ``text``)."""

    kind = DriverKind.EVALS_REPORTER
    default_driver = EvalsReporterDriver.TEXT


@register_driver(DriverKind.EVALS_REPORTER, EvalsReporterDriver.TEXT)
class TextReporterDriver(Driver):
    def build(self) -> TextReporter:
        return TextReporter()
@register_driver(DriverKind.EVALS_REPORTER, EvalsReporterDriver.JSON)
class JsonReporterDriver(Driver):
    def build(self) -> JsonReporter:
        return JsonReporter()
@register_driver(DriverKind.EVALS_REPORTER, EvalsReporterDriver.PYDANTIC)
class PydanticReporterDriver(Driver):
    def build(self) -> PydanticReporter:
        return PydanticReporter()
def assert_trajectory(
    result: Any,
    *,
    calls: list[str] | None = None,
    forbid: list[str] | None = None,
    order: list[str] | None = None,
) -> None:
    """Assert a :class:`ChatResult`'s tool-call trajectory.

    ``calls``/``forbid`` check membership; ``order`` checks that the listed tools
    appear in that relative order.
    """
    trajectory = list(getattr(result, "tool_calls", None) or [])
    for tool in calls or []:
        if tool not in trajectory:
            raise AssertionError(f"tool {tool!r} was not called (called: {trajectory})")
    for tool in forbid or []:
        if tool in trajectory:
            raise AssertionError(f"tool {tool!r} should not have been called")
    if order:
        positions = [trajectory.index(tool) for tool in order if tool in trajectory]
        if len(positions) != len(order) or positions != sorted(positions):
            raise AssertionError(f"tools {order} were not called in order (called: {trajectory})")
