"""Project scaffolding for ``agentkit new``.

``scaffold_project`` writes the full-stack project by default (``full=True``) and
the minimal skeleton otherwise. The templates live in :mod:`minimal` and
:mod:`full`.
"""

from __future__ import annotations

from agentkit.foundation.scaffold.full import (
    FULL_FILES,
    PRESETS,
    preset_files,
    scaffold_project,
)
from agentkit.foundation.scaffold.minimal import (
    MINIMAL_FILES,
    PROJECT_FILES,
    package_name,
    pascal,
)

__all__ = [
    "FULL_FILES",
    "MINIMAL_FILES",
    "PRESETS",
    "PROJECT_FILES",
    "package_name",
    "pascal",
    "preset_files",
    "scaffold_project",
]
