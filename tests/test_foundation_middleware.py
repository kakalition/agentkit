"""WS4 — class-based middleware: groups, aliases, provider registration."""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import App, Middleware, MiddlewareGroup, Provider
from agentkit.foundation.middleware import LoggingMiddleware
from agentkit.runtime import Runtime


class TagMiddleware(Middleware):
    def __init__(self, record: list[str], tag: str) -> None:
        self.record = record
        self.tag = tag

    async def handle(self, turn: Any, call_next: Any) -> Any:
        self.record.append(self.tag)
        return await call_next()


def _app(runtime: Runtime) -> App:
    app = App(name="mw", settings=runtime.settings, discover=False)
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    from agentkit.foundation.agent import Agent as _Agent

    app.agent(_Agent.make("mw").instructions("x").output(str))
    app.boot()
    return app


def test_middleware_group_alias_expands(runtime: Runtime) -> None:
    app = App(name="mw", settings=runtime.settings, discover=False)
    seen: list[str] = []
    app.middleware_group("web", TagMiddleware(seen, "a"), TagMiddleware(seen, "b"))
    app.middleware("web")
    assert len(app.middlewares()) == 2


async def test_group_middleware_runs_in_turn(runtime: Runtime) -> None:
    app = _app(runtime)
    seen: list[str] = []
    app.middleware_group("web", TagMiddleware(seen, "outer"))
    app.middleware("web")
    app.middleware(TagMiddleware(seen, "inner"))
    await app.run("hi")
    assert seen == ["outer", "inner"]


async def test_provider_contributes_middleware(runtime: Runtime) -> None:
    seen: list[str] = []

    class AuditProvider(Provider):
        def register(self, app: App) -> None:  # noqa: ARG002
            return None

        def middleware(self) -> list[Any]:
            return [TagMiddleware(seen, "provider")]

    app = App(name="mw", settings=runtime.settings, discover=False)
    app.providers([AuditProvider])
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    from agentkit.foundation.agent import Agent as _Agent

    app.agent(_Agent.make("mw").instructions("x").output(str))
    app.boot()
    await app.run("hi")
    assert seen == ["provider"]


async def test_logging_middleware_class(runtime: Runtime) -> None:
    app = _app(runtime)
    app.middleware(LoggingMiddleware())
    result = await app.run("hi")
    assert result is not None


def test_unknown_middleware_alias_raises(runtime: Runtime) -> None:
    app = App(name="mw", settings=runtime.settings, discover=False)
    try:
        app.middleware("nope")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_middleware_group_iterable() -> None:
    group = MiddlewareGroup("g", [TagMiddleware([], "x")])
    assert len(list(group)) == 1
    assert group.name == "g"
