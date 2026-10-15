"""Serve an MCP server (FastMCP) with loopback-by-default binding."""

from __future__ import annotations

from typing import Any

from agentkit.guardrails import warn_if_exposed

TRANSPORTS = {"stdio": "stdio", "streamable-http": "http", "http": "http", "sse": "sse"}


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


__all__ = ["TRANSPORTS", "attach_mcp_auth", "serve_mcp"]
