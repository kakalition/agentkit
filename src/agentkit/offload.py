"""Offload large tool outputs to disk, keeping a short preview in history.

A single tool can return far more text than belongs in a conversation. When
``tool_output_offload_threshold`` is set, :func:`offload_messages` writes every
over-threshold tool return under ``<agent_home>/artifacts/offload/<conversation>/``
and replaces it in the (persisted) history with a head/tail preview plus the path,
so the agent can fetch the full text later with the ``read_artifact`` tool.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ToolReturnPart

__all__ = ["PREVIEW_HEAD", "PREVIEW_TAIL", "attach_artifacts", "estimate_tokens", "offload_messages"]

PREVIEW_HEAD = 800
PREVIEW_TAIL = 400


def estimate_tokens(text: str) -> int:
    """A cheap token estimate (~4 characters per token)."""
    return max(1, len(text) // 4)


def _safe_component(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z._-]+", "_", value).strip("_") or "x"


def offload_messages(
    messages: list[ModelMessage],
    *,
    root: str | Path,
    conversation_id: str,
    threshold_tokens: int,
    head: int = PREVIEW_HEAD,
    tail: int = PREVIEW_TAIL,
) -> int:
    """Write over-threshold tool returns under ``root`` and preview them in place.

    Returns the number of messages offloaded. A non-positive ``threshold_tokens``
    is a no-op.
    """
    if threshold_tokens <= 0:
        return 0
    target_dir = Path(root) / "offload" / _safe_component(conversation_id)
    count = 0
    for message in messages:
        for part in getattr(message, "parts", []):
            if not isinstance(part, ToolReturnPart):
                continue
            content = getattr(part, "content", None)
            if not isinstance(content, str) or estimate_tokens(content) <= threshold_tokens:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / f"{_safe_component(str(part.tool_call_id or 'call'))}.txt"
            path.write_text(content, encoding="utf-8")
            preview = content[:head]
            if len(content) > head + tail:
                preview += "\n…\n" + content[-tail:]
            part.content = (
                f"{preview}\n\n[full output (~{estimate_tokens(content)} tokens) offloaded to "
                f"{path}; read it with read_artifact(path={str(path)!r})]"
            )
            count += 1
    return count


def attach_artifacts(agent: Any, root: str | Path) -> Any:
    """Attach the ``read_artifact`` tool (idempotent), confined to ``root``."""
    if getattr(agent, "_agentkit_artifacts_attached", False):
        return agent
    base = Path(root).expanduser().resolve()

    @agent.tool
    async def read_artifact(ctx: RunContext[Any], path: str) -> str:
        """Read a previously offloaded tool output in full.

        Args:
            path: The artifact path reported in an offload preview.
        """
        resolved = Path(path).expanduser().resolve()
        if resolved != base and base not in resolved.parents:
            return "ERROR: path is outside the artifacts directory"
        if not resolved.is_file():
            return "ERROR: no artifact at that path"
        return resolved.read_text(encoding="utf-8")

    agent._agentkit_artifacts_attached = True  # type: ignore[attr-defined]
    return agent
