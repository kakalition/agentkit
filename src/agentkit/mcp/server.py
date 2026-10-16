"""Serve an MCP server (FastMCP) with loopback-by-default binding."""

from __future__ import annotations

from typing import Any

from agentkit.errors import ConfigurationError
from agentkit.guardrails import warn_if_exposed

TRANSPORTS = {"stdio": "stdio", "streamable-http": "http", "http": "http", "sse": "sse"}


def build_agent_mcp_server(app: Any, *, name: str | None = None) -> Any:
    """Build a FastMCP server exposing the app's agent as an ``ask`` tool.

    Requires ``fastmcp`` (a core dependency); raises
    :class:`~agentkit.errors.ConfigurationError` when it is unavailable.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - fastmcp is a core dep
        raise ConfigurationError("serving an agent over MCP needs the 'mcp' extra") from exc

    server = FastMCP(name or getattr(app, "name", None) or "agentkit")

    @server.tool
    async def ask(prompt: str, conversation_id: str = "mcp:default") -> str:
        """Ask the agent a question and return its reply.

        Args:
            prompt: The user message.
            conversation_id: The conversation to keep history under.
        """
        result = await app.answer(conversation_id, prompt)
        return getattr(result, "output", str(result))

    return server


def serve_agent(
    app: Any,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    authenticator: Any = None,
    name: str | None = None,
) -> None:
    """Serve a booted app's agent over MCP (``ask`` tool)."""
    serve_mcp(
        build_agent_mcp_server(app, name=name),
        transport=transport,
        host=host,
        port=port,
        authenticator=authenticator,
    )


def attach_mcp_auth(server: Any, authenticator: Any) -> bool:
    """Wire an :class:`~agentkit.security.authenticator.Authenticator` into FastMCP.

    Only meaningful for HTTP transports. Returns ``True`` when a token verifier
    was attached; ``False`` when FastMCP exposes no auth surface (stdio has none).
    """
    if not getattr(authenticator, "enabled", False):
        return False
    try:
        from fastmcp.server.auth import AccessToken, TokenVerifier
    except Exception:  # pragma: no cover - fastmcp without auth module
        return False

    class _AuthenticatorVerifier(TokenVerifier):
        async def verify_token(self, token: str) -> AccessToken | None:
            actor = await authenticator.resolve_token(token)
            if actor is None:
                return None
            return AccessToken(
                token=token,
                client_id=actor.subject or actor.owner_id,
                scopes=sorted(actor.roles),
                subject=actor.subject or actor.owner_id,
                claims={"owner_id": actor.owner_id, "roles": sorted(actor.roles)},
            )

    server.auth = _AuthenticatorVerifier()
    return True


def serve_mcp(
    server: Any,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    authenticator: Any = None,
) -> None:
    """Run a FastMCP server. HTTP transports warn if not bound to loopback."""
    if transport not in TRANSPORTS:
        raise ValueError(f"unsupported transport: {transport!r}")
    if transport != "stdio":
        warn_if_exposed(host, "the MCP server")
        if authenticator is not None:
            attach_mcp_auth(server, authenticator)
        server.run(transport=TRANSPORTS[transport], host=host, port=port)
    else:
        server.run(transport="stdio")


__all__ = [
    "TRANSPORTS",
    "attach_mcp_auth",
    "build_agent_mcp_server",
    "serve_agent",
    "serve_mcp",
]
