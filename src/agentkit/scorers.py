"""Online scoring: grade live run traces with registered graders.

A run's events (``run_events``) are already recorded for the Playground. When
online scoring is enabled (``online_scoring_enabled``), those traces can be
graded with any registered grader (``online_scoring_grader``, default ``trace``)
and the score is recorded as an ``eval_runs`` row — the same substrate the CLI
and Studio read.

    result = await app.online_scorer.score(repos, run_id)
    # {"run_id": ..., "passed": True, "score": 1.0, "reason": "", "record_id": 3}
"""

from __future__ import annotations

import json
from typing import Any

from agentkit.graders import grader_by_name, run_grader
from agentkit.runs import RunEvent

__all__ = ["OnlineScorer", "score_run"]


async def _events_for(repos: Any, run_id: str) -> list[RunEvent]:
    store = getattr(repos, "run_events", None)
    if store is None:
        return []
    events: list[RunEvent] = []
    for record in await store.events(run_id):
        try:
            events.append(RunEvent.from_dict(json.loads(record.data or "{}")))
        except ValueError:  # pragma: no cover - tolerate corrupt rows
            continue
    return events


def _case_from(events: list[RunEvent]) -> dict[str, Any]:
    """A grader case derived from the trace (declared tools + final output)."""
    tools = [event.tool for event in events if event.kind == "tool" and event.tool]
    output = ""
    for event in reversed(events):
        if event.kind == "final":
            output = str(event.data.get("output", "") or "")
            break
    return {"calls": tools, "output": output}


async def score_run(
    repos: Any,
    run_id: str,
    *,
    grader: Any = None,
    grader_name: str = "trace",
    dataset: str | None = None,
) -> dict[str, Any]:
    """Grade a stored run trace and record the score; returns the score view."""
    events = await _events_for(repos, run_id)
    if not events:
        return {
            "run_id": run_id,
            "passed": False,
            "score": 0.0,
            "reason": "no run events",
            "tool_calls": [],
            "events": 0,
            "record_id": None,
        }
    chosen = grader or grader_by_name(grader_name) or grader_by_name("trace")
    case = _case_from(events)
    # ``trace`` graders take the events; text graders take the final output.
    subject: Any = events
    if chosen is not None and getattr(chosen, "name", "") not in {"trace"}:
        subject = case["output"]
    result = await run_grader(chosen, case, subject)
    record = None
    if getattr(repos, "eval_runs", None) is not None:
        record = await repos.eval_runs.add(
            dataset or f"online:{run_id}",
            passed=result.passed,
            report={
                "run_id": run_id,
                "score": result.score,
                "reason": result.reason,
                "tool_calls": case["calls"],
                "events": len(events),
            },
        )
    return {
        "run_id": run_id,
        "passed": result.passed,
        "score": result.score,
        "reason": result.reason,
        "tool_calls": case["calls"],
        "events": len(events),
        "record_id": getattr(record, "id", None),
    }


class OnlineScorer:
    """Scores run traces with the app's configured grader (``online_scoring_grader``)."""

    def __init__(self, app: Any = None, *, settings: Any = None) -> None:
        self.app = app
        self._settings = settings

    @property
    def settings(self) -> Any:
        if self._settings is not None:
            return self._settings
        return getattr(self.app, "settings", None)

    @property
    def grader_name(self) -> str:
        return str(getattr(self.settings, "online_scoring_grader", "trace") or "trace")

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "online_scoring_enabled", False))

    def grader(self) -> Any:
        """The configured grader, falling back to the eval-grader driver then trace."""
        name = self.grader_name
        chosen = grader_by_name(name)
        if chosen is not None:
            return chosen
        if self.app is not None:
            try:
                return self.app.manager("eval_grader").driver()
            except Exception:  # pragma: no cover - defensive
                pass
        return grader_by_name("trace")

    async def score(
        self, repos: Any, run_id: str, *, grader: Any = None, dataset: str | None = None
    ) -> dict[str, Any]:
        return await score_run(
            repos,
            run_id,
            grader=grader or self.grader(),
            grader_name=self.grader_name,
            dataset=dataset,
        )
