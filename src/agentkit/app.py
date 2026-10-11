"""A high-level facade that wires settings -> runtime -> deps -> chat runner.

    from agentkit import AgentApp
    app = AgentApp(agent=my_orchestrator_agent, settings=AgentSettings())
    result = await app.run("hello")
    print(result.output)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

from agentkit.config import AgentSettings, build_model, get_settings
from agentkit.db.repositories import Repositories
from agentkit.deps import ApprovalCallback, Deps
from agentkit.runtime import Runtime, build_deps, build_runtime, repositories
from agentkit.session import ChatResult, ChatRunner


@dataclass
class AgentApp:
    settings: AgentSettings
    agent: Agent[Any, str]
    runtime: Runtime
    mcp: Any = None
    a2a: Any = None
    model: Any = None

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
        settings = settings or get_settings()
        return cls(
            settings=settings,
            agent=agent,
            runtime=build_runtime(settings, repos_factory=repos_factory),
            mcp=mcp,
            a2a=a2a,
            model=model,
        )

    # -- deps -----------------------------------------------------------
    def repositories(self):
        return repositories(self.runtime)

    def deps(self, repos: Repositories, *, approve: ApprovalCallback | None = None) -> Deps:
        return build_deps(
            self.runtime,
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
