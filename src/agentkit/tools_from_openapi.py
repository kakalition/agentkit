"""Turn an OpenAPI specification into agent-callable HTTP tools.

Each operation becomes an async tool that takes a single ``params`` mapping and
issues the corresponding HTTP request (path/query/body resolved from the spec).
Optional: pass an ``httpx.AsyncClient`` (or any object with ``request``) to reuse
a connection pool and to make the tools testable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SAFE = re.compile(r"[^0-9a-zA-Z_]+")


def _load_spec(spec: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec, dict):
        return spec
    text = Path(spec).read_text(encoding="utf-8")
    if str(spec).endswith((".yaml", ".yml")):
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


def _safe_name(value: str, fallback: str) -> str:
    name = SAFE.sub("_", value or "").strip("_")
    return name or fallback


class OpenAPIToolkit:
    """Compile an OpenAPI document into a set of callable tools."""

    def __init__(
        self,
        spec: str | Path | dict[str, Any],
        *,
        base_url: str | None = None,
        methods: tuple[str, ...] = ("get", "post", "put", "patch", "delete"),
        include: list[str] | None = None,
        headers: dict[str, str] | None = None,
        client: Any = None,
        timeout: float = 30.0,
        max_chars: int = 4000,
    ) -> None:
        self.spec = _load_spec(spec)
        self.base_url = (base_url or self._default_base_url()).rstrip("/")
        self.methods = methods
        self.include = include
        self.headers = headers or {}
        self._client = client
        self.timeout = timeout
        self.max_chars = max_chars
        self._operations = self._compile()

    def _default_base_url(self) -> str:
        servers = self.spec.get("servers") or []
        if servers and isinstance(servers[0], dict):
            return str(servers[0].get("url", ""))
        return ""

    def _compile(self) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        for path, item in (self.spec.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            for method, operation in item.items():
                if method.lower() not in self.methods or not isinstance(operation, dict):
                    continue
                op_id = operation.get("operationId") or f"{method}_{path}"
                name = _safe_name(op_id, _safe_name(f"{method}_{path}", "op"))
                if self.include and name not in self.include and op_id not in self.include:
                    continue
                operations.append(
                    {
                        "name": name,
                        "method": method.upper(),
                        "path": path,
                        "summary": operation.get("summary") or operation.get("description") or op_id,
                    }
                )
        return operations

    def operations(self) -> list[dict[str, Any]]:
        return list(self._operations)

    def tools(self) -> list[Any]:
        return [self._make_tool(op) for op in self._operations]

    def _make_tool(self, op: dict[str, Any]) -> Any:
        async def _tool(params: dict[str, Any] | None = None) -> str:
            return await self.invoke(op["name"], params or {})

        _tool.__name__ = op["name"]
        _tool.__doc__ = (
            f"{op['summary']}\n\nArgs:\n    params: Path/query/body values for the request."
        )
        return _tool

    async def invoke(self, name: str, params: dict[str, Any]) -> str:
        op = next((item for item in self._operations if item["name"] == name), None)
        if op is None:
            return f"ERROR: unknown operation {name!r}"
        path = op["path"]
        remaining = dict(params)
        for token in re.findall(r"\{([^}]+)\}", path):
            if token in remaining:
                path = path.replace("{" + token + "}", str(remaining.pop(token)))
        url = f"{self.base_url}{path}"
        request_kwargs: dict[str, Any] = {"method": op["method"], "url": url}
        if op["method"] in {"GET", "DELETE"}:
            request_kwargs["params"] = remaining or None
        else:
            request_kwargs["json"] = remaining or None
        request_kwargs["headers"] = self.headers
        request_kwargs["timeout"] = self.timeout
        try:
            response = await self._request(request_kwargs)
            text = response.text
        except Exception as exc:  # network failure → tool error string
            return f"ERROR: {type(exc).__name__}: {exc}"
        if len(text) > self.max_chars:
            text = text[: self.max_chars] + "…"
        return text

    async def _request(self, kwargs: dict[str, Any]) -> Any:
        if self._client is not None:
            return await self._client.request(**kwargs)
        import httpx

        async with httpx.AsyncClient() as client:
            return await client.request(**kwargs)


def tools_from_openapi(spec: str | Path | dict[str, Any], **options: Any) -> list[Any]:
    """Convenience: compile ``spec`` and return the list of tool callables."""
    return OpenAPIToolkit(spec, **options).tools()


def register_openapi_tools(agent: Any, spec: str | Path | dict[str, Any], **options: Any) -> Any:
    """Attach every OpenAPI operation as a tool on a built agent."""
    toolkit = OpenAPIToolkit(spec, **options)
    for tool in toolkit.tools():
        agent.tool(tool)
    agent._agentkit_openapi = toolkit  # type: ignore[attr-defined]
    return agent


__all__ = ["OpenAPIToolkit", "register_openapi_tools", "tools_from_openapi"]
