"""T7 — no inert settings: every AgentSettings field is read somewhere in ``src/``.

The declaration in ``config.py`` counts as one occurrence; a real read is a second
occurrence. Settings that exist only for introspection or as user-facing defaults
consumed outside ``src`` belong in the (deliberately minimal) allow-list below.
"""

from __future__ import annotations

import re
from pathlib import Path

from agentkit.config import AgentSettings

SRC = Path(__file__).resolve().parents[1] / "src"

#: Intentionally informational / introspection-only settings (none today: every
#: field is read by source). Add a field here only with a documented reason.
INFORMATIONAL: frozenset[str] = frozenset()


def _source_text() -> str:
    return "\n".join(path.read_text() for path in SRC.rglob("*.py"))


def test_every_setting_is_read_in_source() -> None:
    text = _source_text()
    inert = [
        field
        for field in AgentSettings.model_fields
        if field not in INFORMATIONAL
        and len(re.findall(rf"\b{re.escape(field)}\b", text)) < 2
    ]
    assert not inert, f"settings never read outside their declaration: {sorted(inert)}"


def test_allow_list_is_minimal() -> None:
    assert all(name in AgentSettings.model_fields for name in INFORMATIONAL)
