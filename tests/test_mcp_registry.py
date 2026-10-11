from __future__ import annotations

from fastmcp import FastMCP

from agentkit.mcp.registry import MCPRegistry, MCPServerSpec, first_out


def _server() -> FastMCP:
    server = FastMCP("demo")

    @server.tool
    def render(spec: dict) -> dict:
        """Render."""
        return {"out": "/tmp/x.png", "bytes": 1}

    @server.resource("demo://schema")
    def schema() -> str:
        return "the-schema"

    return server


async def test_registry_call_and_resource(tmp_path):
    registry = MCPRegistry([MCPServerSpec(name="chart", transport=_server())], log_dir=tmp_path)
    async with registry:
        assert registry.available
        result = await registry.call_tool("chart", "render", {"spec": {}})
        assert first_out(result) == "/tmp/x.png"
        assert await registry.read_resource("chart", "demo://schema") == "the-schema"


async def test_registry_prefixed_tool_names(tmp_path):
    registry = MCPRegistry([MCPServerSpec(name="chart", transport=_server())], log_dir=tmp_path)
    async with registry:
        names = await registry.tool_names()
    assert names == ["chart:render"]


async def test_unknown_server_raises(tmp_path):
    registry = MCPRegistry([], log_dir=tmp_path)
    async with registry:
        try:
            await registry.call_tool("missing", "x", {})
        except RuntimeError as exc:
            assert "missing" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected RuntimeError")
