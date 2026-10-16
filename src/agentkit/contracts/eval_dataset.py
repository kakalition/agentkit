"""The eval dataset + grader contracts.

A :class:`Dataset` is a named collection of cases (optionally loaded from a
source) that materializes into an :class:`~agentkit.evals.EvalSuite`. A
:class:`Grader` scores one case output (or a stored run trace) — reference graders
are exact-match, contains, schema, and an LLM judge.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Dataset", "GradeResult", "Grader"]


@runtime_checkable
class Dataset(Protocol):
    """A named collection of evaluation cases."""

    name: str

    def cases(self) -> list[Any]: ...

    def to_suite(self) -> Any: ...


@runtime_checkable
class Grader(Protocol):
    """Score a case output against an expectation."""

    name: str

    def grade(self, case: Any, output: Any) -> Any: ...


class GradeResult:
    """The outcome of one grading: ``passed`` plus a score and reason."""

    __slots__ = ("reason", "score", "passed")

    def __init__(self, passed: bool, score: float = 1.0, reason: str = "") -> None:
        self.passed = bool(passed)
        self.score = float(score)
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "score": self.score, "reason": self.reason}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"GradeResult(passed={self.passed}, score={self.score}, reason={self.reason!r})"
