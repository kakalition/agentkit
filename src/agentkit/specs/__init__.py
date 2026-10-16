"""The unified spec layer: agent / team / workflow / eval definitions.

A *spec* is the serializable half of a subsystem object; the
:data:`~agentkit.specs.registry.SPECS` registry maps a spec kind to its pydantic
model, JSON Schema, materializer, and codegen targets. Definitions persist in the
``definitions`` table via :class:`~agentkit.specs.store.RepositorySpecStore`::

    from agentkit.specs import SPECS, SpecKind

    SPECS.schema_for(SpecKind.TEAM)
    agent = SPECS.materialize(SpecKind.AGENT, {"name": "researcher"})
"""

# Importing the spec modules registers each kind (and its python codegen).
from agentkit.specs.base import SpecKind, SpecModel
from agentkit.specs.codegen import (
    CodegenTarget,
    register_codegen,
    register_python_renderer,
    render_spec,
    targets,
)
from agentkit.specs.registry import SPECS, SpecEntry, SpecRegistry, register_spec
from agentkit.specs.store import RepositorySpecStore, SpecStore

__all__ = [
    "SPECS",
    "AgentDefinition",
    "CodegenTarget",
    "RepositorySpecStore",
    "SpecEntry",
    "SpecKind",
    "SpecModel",
    "SpecRegistry",
    "SpecStore",
    "WorkflowDefinition",
    "WorkflowNode",
    "EvalDefinition",
    "TeamDefinition",
    "register_codegen",
    "register_python_renderer",
    "register_spec",
    "render_spec",
    "targets",
]

# -- built-in Studio panels (WS3) ---------------------------------------
# Registered here so a spec kind (even one added by an extension) can carry a
# panel; the SPA renders unknown panels with the generic schema-form renderer.
from agentkit.extensions.panels import PanelSpec, register_panel  # noqa: E402

_BUILTIN_PANELS = (
    PanelSpec(id="agents", title="Agents", spec_kind="agent", order=10, layout="form"),
    PanelSpec(id="teams", title="Teams", spec_kind="team", order=20, layout="builder"),
    PanelSpec(
        id="workflows",
        title="Workflows",
        spec_kind="workflow",
        order=30,
        layout="workflow-canvas",
    ),
    PanelSpec(id="evals", title="Evals", spec_kind="eval", order=40, layout="form"),
    PanelSpec(id="catalog", title="Catalog", order=50, layout="catalog-browser"),
    PanelSpec(id="traces", title="Traces", order=60, layout="traces"),
    PanelSpec(id="playground", title="Playground", order=90, layout="playground-flow"),
)
for _panel in _BUILTIN_PANELS:
    register_panel(_panel)

# Late imports so the class re-exports above stay cheap to read.
from agentkit.specs.agent import AgentDefinition  # noqa: E402
from agentkit.specs.eval import EvalDefinition  # noqa: E402
from agentkit.specs.team import TeamDefinition  # noqa: E402
from agentkit.specs.workflow import WorkflowDefinition, WorkflowNode  # noqa: E402
