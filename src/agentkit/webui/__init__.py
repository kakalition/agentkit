"""In-core operator web UI, served by the agent process itself.

Every agentkit agent gets it for free: :func:`agentkit.supervise.run_all`
auto-appends the :func:`webui_service` when the agent's settings enable it. The
backend reuses the agent's own ``Runtime``/``Repositories``/``scheduler``/
``durability``/SOUL, so it manages only the hosting agent.
"""

from __future__ import annotations

from agentkit.webui.app import build_webui_app
from agentkit.webui.context import Answer, WebUIContext
from agentkit.webui.server import serve_webui, webui_service

__all__ = [
    "Answer",
    "WebUIContext",
    "build_webui_app",
    "serve_webui",
    "webui_service",
]
