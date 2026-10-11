"""Serve an MCP server (FastMCP) with loopback-by-default binding."""

from __future__ import annotations

from typing import Any

from agentkit.guardrails import warn_if_exposed

TRANSPORTS = {"stdio": "stdio", "streamable-http": "http", "http": "http", "sse": "sse"}


def serve_mcp(
    server: Any,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Run a FastMCP server. HTTP transports warn if not bound to loopback."""
    if transport not in TRANSPORTS:
        raise ValueError(f"unsupported transport: {transport!r}")
    if transport != "stdio":
        warn_if_exposed(host, "the MCP server")
        server.run(transport=TRANSPORTS[transport], host=host, port=port)
    else:
        server.run(transport="stdio")
