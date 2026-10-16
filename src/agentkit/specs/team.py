"""The ``team`` spec — :class:`~agentkit.studio.TeamDefinition` registered as a spec.

``TeamDefinition`` predates the spec layer; registering it under
:data:`SpecKind.TEAM` (without renaming it) unifies the ``definitions`` store while
keeping the public ``agentkit.studio.TeamDefinition`` surface and the
``/api/studio/teams`` endpoints working.
"""

from __future__ import annotations

from typing import Any

from agentkit.specs.base import SpecKind
from agentkit.specs.codegen import register_python_renderer
from agentkit.specs.registry import SPECS
from agentkit.studio import (
    TeamDefinition,
    materialize_team,
    render_team_code,
    resolve_from_app,
    run_team_definition,
)

__all__ = ["materialize_team_spec", "render_team_code", "run_team_spec"]


def materialize_team_spec(
    definition: TeamDefinition,
    *,
    app: Any = None,
    resolve: Any = None,
) -> Any:
    """Build a runnable team runner from a definition."""
    if resolve is None and app is not None:
        resolve = resolve_from_app(app)
    return materialize_team(definition, resolve)


async def run_team_spec(
    definition: TeamDefinition,
    prompt: str,
    *,
    app: Any = None,
    resolve: Any = None,
    ctx: Any = None,
    recorder: Any = None,
) -> dict[str, Any]:
    """Run a team definition and return the plain result dict."""
    if resolve is None and app is not None:
        resolve = resolve_from_app(app)
    return await run_team_definition(definition, prompt, resolve=resolve, ctx=ctx, recorder=recorder)


def _render_python(definition: TeamDefinition) -> str:
    return render_team_code(definition)


SPECS.register(
    SpecKind.TEAM,
    TeamDefinition,
    materializer=materialize_team_spec,
    runner=run_team_spec,
)
register_python_renderer(SpecKind.TEAM, _render_python)
