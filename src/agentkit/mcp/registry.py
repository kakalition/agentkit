"""MCP client registry: own N MCP toolsets for the process lifetime.

Each server is exposed as a prefixed toolset (``<name>_<tool>``) so servers that
share tool names do not collide. HTTP servers are addressed by URL; stdio
servers are launched directly. The registry is entered once and closed on
shutdown — a long-running bot must not open a subprocess per message.
"""

from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp import Client as FastMCPClient
from pydantic_ai.mcp import MCPToolset, StdioTransport


@dataclass
class MCPServerSpec:
    """How to reach one MCP server and how to prefix its tools."""

    name: str  # tool prefix, e.g. "chart" -> chart_render_chart
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    # A prebuilt transport/client/FastMCP server (used by tests).
    transport: Any = None
    env: dict[str, str] | None = None
    log_var: str | None = None  # env var to set the server's log level
    log_file: str | None = None  # child stderr log file name (under log_dir)
    include_instructions: bool = True
    mode: str = "auto"  # FastMCP client negotiation: auto | legacy | stateless


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n\n".join(_text(v) for v in value)
    data = getattr(value, "data", None)
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(value)


def extract_metadata_blocks(result: Any) -> list[dict[str, Any]]:
    """Pull JSON metadata blocks out of an MCP tool result (e.g. an ``out`` path)."""
    blocks: list[dict[str, Any]] = []
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        blocks.append(structured)
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


class MCPRegistry:
    def __init__(self, specs: list[MCPServerSpec], *, log_dir: Path | None = None) -> None:
        self.specs = specs
        self.log_dir = log_dir
        self._stack: AsyncExitStack | None = None
        self._raw: dict[str, MCPToolset] = {}
        self.toolsets_by_name: dict[str, Any] = {}
        self.schemas: dict[str, str] = {}
        self.errors: dict[str, str] = {}

    # -- construction ----------------------------------------------------
    def _transport(self, spec: MCPServerSpec) -> Any:
        if spec.transport is not None:
            return spec.transport
        if spec.url:
            return spec.url
        env = dict(spec.env or {})
        merged = {**os.environ, **env}
        if spec.log_var:
            merged[spec.log_var] = merged.get(spec.log_var, "ERROR")
        merged.pop("VIRTUAL_ENV", None)
        kwargs: dict[str, Any] = {}
        if spec.log_file and self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            kwargs["log_file"] = self.log_dir / spec.log_file
        return StdioTransport(command=spec.command or "", args=spec.args, env=merged, **kwargs)

    def _toolset(self, spec: MCPServerSpec) -> MCPToolset:
        client = FastMCPClient(self._transport(spec), mode=spec.mode)  # type: ignore[arg-type]
        return MCPToolset(client, include_instructions=spec.include_instructions)

    def build(self) -> None:
        for spec in self.specs:
            raw = self._toolset(spec)
            self._raw[spec.name] = raw
            self.toolsets_by_name[spec.name] = raw.prefixed(spec.name)

    # -- lifecycle -------------------------------------------------------
    async def __aenter__(self) -> MCPRegistry:
        self.build()
        self._stack = AsyncExitStack()
        for spec in self.specs:
            try:
                await self._stack.enter_async_context(self.toolsets_by_name[spec.name])
            except Exception as exc:  # pragma: no cover - external servers
                self.errors[spec.name] = f"{type(exc).__name__}: {exc}"
                self.toolsets_by_name.pop(spec.name, None)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    # -- accessors -------------------------------------------------------
    def toolsets(self) -> list[Any]:
        return list(self.toolsets_by_name.values())

    @property
    def available(self) -> bool:
        return bool(self.toolsets_by_name)

    async def read_resource(self, name: str, uri: str) -> str:
        raw = self._raw.get(name)
        if raw is None:
            raise RuntimeError(f"unknown MCP server: {name}")
        text = _text(await raw.read_resource(uri))
        self.schemas[uri] = text
        return text

    async def call_tool(self, name: str, tool: str, arguments: dict[str, Any]) -> Any:
        raw = self._raw.get(name)
        if raw is None:
            raise RuntimeError(f"MCP server '{name}' is not available")
        return await raw.client.call_tool(tool, arguments)

    async def tool_names(self) -> list[str]:
        names: list[str] = []
        for name, raw in self._raw.items():
            try:
                tools = await raw.client.list_tools()
                names.extend(f"{name}:{tool.name}" for tool in tools)
            except Exception as exc:  # pragma: no cover
                self.errors[f"{name}:tools"] = f"{type(exc).__name__}: {exc}"
        return names


def first_out(result: Any) -> str | None:
    """Return the artifact path from an MCP tool result, if any."""
    data = getattr(result, "data", None)
    if isinstance(data, dict) and (data.get("out") or data.get("path")):
        return str(data.get("out") or data.get("path"))
    for block in extract_metadata_blocks(result):
        found = block.get("out") or block.get("path")
        if found:
            return str(found)
    return None
