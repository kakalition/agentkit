"""Deprecated shim: :class:`AgentApp` over the new :class:`~agentkit.foundation.App`.

The old dataclass-style surface is preserved exactly (``settings``, ``agent``,
``runtime``, ``mcp``, ``a2a``, ``model``; ``build``/``deps``/``repositories``/
``run``). It now delegates to an internal :class:`App`, so facades and events
work through it too.

    from agentkit import AgentApp
    app = AgentApp.build(agent=my_orchestrator_agent, settings=AgentSettings())
    result = await app.run("hello")
    print(result.output)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent

from agentkit.config import AgentSettings, build_model, get_settings
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback, Deps
from agentkit.foundation.application import App
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.session import ChatResult, ChatRunner


@dataclass
class AgentApp:
    settings: AgentSettings
    agent: Agent[Any, str]
    runtime: Runtime | None = None
    mcp: Any = None
    a2a: Any = None
    model: Any = None
    _app: App = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.runtime is None:
            self.runtime = build_runtime(self.settings)
        app = App(
            name=self.settings.agent_name,
            settings=self.settings,
            discover=False,
            model=self.model,
            mcp=self.mcp,
            a2a=self.a2a,
        )
        app.agent(self.agent)
        app._runtime = self.runtime
        object.__setattr__(self, "_app", app)

    @classmethod
    def build(
        cls,
        *,
        agent: Agent[Any, str],
        settings: AgentSettings | None = None,
        repos_factory: type[Repositories] = Repositories,
        mcp: Any = None,
        a2a: Any = None,
        model: Any = None,
    ) -> AgentApp:
        warnings.warn(
            "AgentApp is deprecated; use agentkit.App instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        settings = settings or get_settings()
        return cls(
            settings=settings,
            agent=agent,
            runtime=build_runtime(settings, repos_factory=repos_factory),
            mcp=mcp,
            a2a=a2a,
            model=model,
        )

    @property
    def app(self) -> App:
        """The underlying :class:`App` (for facades, providers, channels)."""
        return self._app

    # -- deps -----------------------------------------------------------
    def repositories(self):
        return repositories(self.runtime)

    def deps(self, repos: Repositories, *, approve: ApprovalCallback | None = None) -> Deps:
        runtime = self.runtime
        assert runtime is not None
        return build_deps(
            runtime,
            repos,
            model=self.model or build_model(self.settings),
            mcp=self.mcp,
            a2a=self.a2a,
            approve=approve,
        )

    # -- run ------------------------------------------------------------
    async def run(
        self,
        text: str,
        *,
        conversation_id: str = "cli:default",
        approve: ApprovalCallback | None = None,
    ) -> ChatResult:
        with self.repositories() as repos:
            runner = ChatRunner(
                self.deps(repos, approve=approve),
                agent=self.agent,
                conversation_id=conversation_id,
            )
            return await runner.send(text)
