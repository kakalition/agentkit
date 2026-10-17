"""Native skill-authoring toolkit: write valid ``SKILL.md`` files on demand.

Both tools require approval. Skills are written into the first registry root
(``settings.skills_dir`` else ``./skills``), re-discovered immediately, and the
front matter is emitted with :func:`agentkit.skills.render_skill_file` so
discovery always parses it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.skills import SkillRegistry, slugify_skill, write_skill_file
from agentkit.toolkits._common import emit_event, settings_of

__all__ = ["_attach_skill_authoring"]


def _registry(ctx: RunContext[Deps]) -> SkillRegistry:
    registry = SkillRegistry.from_settings(settings_of(ctx))
    registry.discover(reload=True)
    return registry


def skill_root(ctx: RunContext[Deps]) -> Path:
    """The directory skills are written into (the first registry root)."""
    registry = _registry(ctx)
    root = registry.roots[0] if registry.roots else Path.cwd() / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _attach_skill_authoring(agent: Any, *, flag: str = "skill_authoring_enabled") -> Any:
    """Register the skill-authoring tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_skill_authoring_attached", False):
        return agent

    @agent.tool(requires_approval=True)
    async def save_skill(
        ctx: RunContext[Deps],
        name: str,
        description: str,
        body: str,
        allowed_tools: list[str] | None = None,
    ) -> str:
        """Create a new skill as a SKILL.md file (requires approval).

        Args:
            name: The skill name (used as the directory name).
            description: A one-line description for the skill index.
            body: The skill's markdown instructions.
            allowed_tools: Optional tools the skill needs.
        """
        slug = slugify_skill(name)
        write_skill_file(
            skill_root(ctx),
            slug,
            description=description,
            body=body,
            allowed_tools=list(allowed_tools or []),
        )
        if slug not in _registry(ctx).names():
            return f"ERROR: wrote {slug!r} but discovery did not parse it"
        await emit_event("skill.saved", name=slug)
        return f"saved skill {slug!r}"

    @agent.tool(requires_approval=True)
    async def update_skill(ctx: RunContext[Deps], name: str, body: str) -> str:
        """Replace an existing skill's body (requires approval).

        Args:
            name: The skill name to update.
            body: The new markdown instructions.
        """
        slug = slugify_skill(name)
        existing = _registry(ctx).get(slug)
        if existing is None:
            return "(no such skill)"
        write_skill_file(
            skill_root(ctx),
            slug,
            description=existing.description,
            body=body,
            allowed_tools=existing.allowed_tools,
        )
        _registry(ctx)
        await emit_event("skill.updated", name=slug)
        return f"updated skill {slug!r}"

    agent._agentkit_skill_authoring_attached = True  # type: ignore[attr-defined]
    return agent
