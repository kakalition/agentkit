"""Plan-and-execute: decompose a goal, then work the steps.

A :class:`Planner` wraps an agent (or any object with ``run``)::

    from agentkit.foundation.agent import Agent
    from agentkit.planning import Planner

    agent = Agent.make("ops").instructions("…").build()
    planner = Planner(agent)
    run = await planner.execute("Plan a launch", deps=deps, model=model)
    for step in run.steps:
        print(step.description, "->", step.result)

:meth:`Planner.plan` returns the :class:`Plan` alone; :meth:`Planner.execute`
runs each step, feeding prior results back in as context.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Plan", "PlanStep", "Planner", "parse_plan"]

PLAN_INSTRUCTIONS = (
    "You are a planner. Decompose the goal into a short, ordered list of concrete "
    "steps. Respond with ONLY a JSON array of strings, e.g. [\"step 1\", \"step 2\"]. "
    "Use at most {max_steps} steps; do not add commentary."
)


@dataclass
class PlanStep:
    description: str
    result: str = ""
    done: bool = False


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return bool(self.steps) and all(step.done for step in self.steps)


def parse_plan(goal: str, text: str, *, max_steps: int = 12) -> Plan:
    """Parse a model's plan text (JSON array, JSON lines, or numbered list)."""
    steps: list[str] = []
    stripped = (text or "").strip()
    for candidate in (stripped, _extract_json_array(stripped)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list):
            steps = [str(item).strip() for item in parsed if str(item).strip()]
            break
        if isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
            steps = [str(item).strip() for item in parsed["steps"] if str(item).strip()]
            break
    if not steps:
        steps = [
            re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
            for line in stripped.splitlines()
            if re.match(r"^\s*([-*]|\d+[.)])\s+", line)
        ]
    if not steps and stripped:
        steps = [stripped]
    return Plan(goal=goal, steps=[PlanStep(description=s) for s in steps[:max_steps]])


def _extract_json_array(text: str) -> str:
    start, end = text.find("["), text.rfind("]")
    if 0 <= start < end:
        return text[start : end + 1]
    return ""


class Planner:
    """Plan a goal and execute the steps with an agent."""

    def __init__(self, agent: Any, *, max_steps: int = 12, on_step: Callable[..., Any] | None = None):
        self.agent = agent
        self.max_steps = max_steps
        self.on_step = on_step

    async def plan(self, goal: str, *, deps: Any = None, model: Any = None) -> Plan:
        prompt = f"{goal}\n\nReturn at most {self.max_steps} steps."
        output = await self._run(prompt, deps=deps, model=model, instructions=PLAN_INSTRUCTIONS)
        return parse_plan(goal, output, max_steps=self.max_steps)

    async def execute(self, goal: str, *, deps: Any = None, model: Any = None) -> Plan:
        plan = await self.plan(goal, deps=deps, model=model)
        for index, step in enumerate(plan.steps, start=1):
            prior = "\n".join(
                f"{i}. {s.description} -> {s.result}" for i, s in enumerate(plan.steps[: index - 1], 1)
            )
            prompt = (
                f"Goal: {goal}\n\nCompleted so far:\n{prior or '(nothing yet)'}\n\n"
                f"Now perform step {index}: {step.description}"
            )
            step.result = await self._run(prompt, deps=deps, model=model)
            step.done = True
            if self.on_step is not None:
                outcome = self.on_step(step, plan)
                if hasattr(outcome, "__await__"):
                    await outcome
        return plan

    async def _run(
        self, prompt: str, *, deps: Any, model: Any, instructions: str | None = None
    ) -> str:
        result = await self.agent.run(prompt, deps=deps, model=model)
        output = getattr(result, "output", result)
        return output if isinstance(output, str) else str(output)
