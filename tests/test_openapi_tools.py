from __future__ import annotations

import httpx

from agentkit.tools_from_openapi import OpenAPIToolkit, tools_from_openapi

SPEC = {
    "openapi": "3.0.0",
    "servers": [{"url": "http://api.local"}],
    "paths": {
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "summary": "Fetch a pet",
                "parameters": [{"name": "petId", "in": "path", "required": True}],
            }
        },
        "/pets": {
            "post": {"operationId": "createPet", "summary": "Create a pet"},
        },
    },
}


def _toolkit(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAPIToolkit(SPEC, client=client)


async def test_invoke_substitutes_path_and_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    toolkit = _toolkit(handler)
    assert {op["name"] for op in toolkit.operations()} == {"getPet", "createPet"}

    get_result = await toolkit.invoke("getPet", {"petId": "7"})
    assert "ok" in get_result
    assert str(seen[0].url) == "http://api.local/pets/7"

    await toolkit.invoke("createPet", {"name": "Rex"})
    assert seen[1].method == "POST"
    import json

    assert json.loads(seen[1].content) == {"name": "Rex"}


async def test_error_is_returned_as_string():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    toolkit = _toolkit(handler)
    result = await toolkit.invoke("getPet", {"petId": "1"})
    assert result.startswith("ERROR:")
    assert "unknown operation" in await toolkit.invoke("nope", {})


def test_tools_carry_names_and_docs():
    tools = tools_from_openapi(SPEC, base_url="http://api.local")
    names = {tool.__name__ for tool in tools}
    assert names == {"getPet", "createPet"}
    assert "Fetch a pet" in tools[0].__doc__
