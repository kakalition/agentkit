from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import jwt
import pytest
from a2a import types as t
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agentkit.a2a.server import TaskAgentExecutor, build_a2a_app, build_card
from agentkit.a2a.task_store import SQLAlchemyTaskStore
from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.errors import PermissionDenied
from agentkit.policy import ToolPolicy
from agentkit.runtime import build_runtime, repositories
from agentkit.security import API_KEY, Actor
from agentkit.security.authenticator import Authenticator, AuthError
from agentkit.security.jwt import JWKSVerifier, JWTError
from agentkit.security.keys import hash_key, parse_api_keys
from agentkit.webui.app import build_webui_app

BASE = "http://test"


def _request(headers=None, params=None):
    return SimpleNamespace(headers=headers or {}, query_params=params or {})


# -- keys -------------------------------------------------------------------
def test_parse_api_keys_json_and_csv():
    specs = parse_api_keys('{"ci": {"key": "sk-1", "owner": "acme", "roles": ["admin", "ops"]}}')
    assert specs[0].owner_id == "acme"
    assert specs[0].roles == ("admin", "ops")
    csv = parse_api_keys("ci:sk-2:acme:admin|ops;ro:sk-3")
    assert csv[0].roles == ("admin", "ops")
    assert csv[1].owner_id == "ro"
    assert parse_api_keys(None) == []
    assert parse_api_keys("{not json") == []


def test_hash_key_is_stable():
    assert hash_key("abc") == hash_key("abc")
    assert hash_key("abc") != hash_key("abd")


# -- authenticator ----------------------------------------------------------
def _auth_settings(tmp_path, **over):
    base: dict = {
        "owner_id": "owner",
        "agent_home": tmp_path,
        "memory_embedding_backend": "hash",
        "auth_enabled": True,
        "auth_api_keys": {"ci": {"key": "secret", "owner": "acme", "roles": ["admin"]}},
    }
    base.update(over)
    return AgentSettings(**base)


async def test_authenticator_disabled_is_permissive(tmp_path):
    settings = AgentSettings(owner_id="owner", agent_home=tmp_path, auth_enabled=False)
    auth = Authenticator(settings)
    actor = await auth.authenticate_request(_request())
    assert actor.owner_id == "owner"
    assert actor.method == "none"


async def test_authenticator_fail_closed_and_static_key(tmp_path):
    auth = Authenticator(_auth_settings(tmp_path))
    assert auth.enabled is True
    with pytest.raises(AuthError):
        await auth.authenticate_request(_request())
    actor = await auth.authenticate_request(
        _request({}, {"access_token": "secret"})
    )
    assert actor.owner_id == "acme"
    assert actor.roles == frozenset({"admin"})
    assert actor.method == API_KEY
    with pytest.raises(AuthError):
        await auth.authenticate_request(_request({"authorization": "Bearer wrong"}))


async def test_authenticator_db_lookup(runtime):
    from agentkit.webui.auth import make_db_lookup

    async with repositories(runtime) as repos:
        await repos.api_keys.create(name="ci", key_hash=hash_key("tok"), roles=["ops"])
    auth = Authenticator(runtime.settings, db_lookup=make_db_lookup(runtime))
    actor = await auth.resolve_token("tok")
    assert actor is not None
    assert actor.roles == frozenset({"ops"})
    assert await auth.resolve_token("nope") is None


# -- jwt --------------------------------------------------------------------
def _jwks_fixture():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public_jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
    return private_pem, {"keys": [public_jwk]}


def _verifier(jwks):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JWKSVerifier(
        jwks_url="http://jwks.local/keys",
        issuer="iss",
        audience="api",
        algorithms=["RS256"],
        client=client,
    )


async def test_jwks_verify_and_reject():
    private_pem, jwks = _jwks_fixture()
    verifier = _verifier(jwks)
    token = jwt.encode(
        {"sub": "alice", "roles": ["admin"], "iss": "iss", "aud": "api"},
        private_pem,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    actor = await verifier.verify(token)
    assert actor.owner_id == "alice"
    assert actor.roles == frozenset({"admin"})

    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad = jwt.encode({"sub": "bob", "iss": "iss", "aud": "api"}, other, algorithm="RS256", headers={"kid": "k1"})
    with pytest.raises(JWTError):
        await verifier.verify(bad)


async def test_jwt_claims_flow_through_authenticator(tmp_path):
    private_pem, jwks = _jwks_fixture()
    settings = _auth_settings(tmp_path, auth_api_keys=None, auth_jwks_url="http://jwks.local/keys")
    auth = Authenticator(settings, jwks_verifier=_verifier(jwks))
    token = jwt.encode(
        {"sub": "alice", "iss": "iss", "aud": "api"}, private_pem, algorithm="RS256", headers={"kid": "k1"}
    )
    actor = await auth.resolve_token(token)
    assert actor is not None and actor.owner_id == "alice"


# -- rbac -------------------------------------------------------------------
def test_tool_policy_require_roles():
    policy = ToolPolicy(require_roles={"danger": {"admin"}})
    policy.check("danger", Actor(owner_id="o", roles=frozenset({"admin"})))
    with pytest.raises(PermissionDenied):
        policy.check("danger", Actor(owner_id="o"))
    with pytest.raises(PermissionDenied):
        policy.check("danger")
    policy.check("safe")


# -- web ui -----------------------------------------------------------------
def test_webui_auth_required_and_whoami(tmp_path):
    settings = _auth_settings(tmp_path)
    runtime = build_runtime(settings)
    app = build_webui_app(runtime=runtime, settings=settings)
    client = TestClient(app)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/whoami").status_code == 401

    ok = client.get("/api/whoami", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["owner_id"] == "acme"
    assert body["roles"] == ["admin"]
    assert body["authenticated"] is True


def test_webui_auth_disabled_whoami_defaults(tmp_path):
    settings = AgentSettings(owner_id="solo", agent_home=tmp_path)
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    body = client.get("/api/whoami").json()
    assert body["owner_id"] == "solo"
    assert body["method"] == "none"


# -- a2a --------------------------------------------------------------------
async def _answer(text: str) -> str:
    return f"echo: {text}"


async def test_a2a_auth_gate(tmp_path):
    settings = _auth_settings(tmp_path)
    auth = Authenticator(settings)
    card = build_card(name="Echo", description="echo", url=BASE)
    app = build_a2a_app(
        card=card,
        executor=TaskAgentExecutor(_answer),
        task_store=SQLAlchemyTaskStore(build_runtime(settings)),
        healthz=lambda: True,
        auth=auth,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=BASE) as http:
        assert (await http.get("/healthz")).status_code == 200
        denied = await http.post("/", json={"jsonrpc": "2.0", "id": "1", "method": "x"})
        assert denied.status_code == 401
        allowed = await http.post(
            "/",
            json={"jsonrpc": "2.0", "id": "1", "method": "x"},
            headers={"Authorization": "Bearer secret"},
        )
        assert allowed.status_code != 401


# -- cli --------------------------------------------------------------------
def test_cli_auth_key_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()
    runner = CliRunner()

    created = runner.invoke(cli_app, ["auth:key", "create", "ci", "--roles", "admin"])
    assert created.exit_code == 0, created.output
    token = created.output.strip().splitlines()[-1]

    listed = runner.invoke(cli_app, ["auth:key", "list"])
    assert listed.exit_code == 0
    assert "ci" in listed.output
    assert token not in listed.output

    revoked = runner.invoke(cli_app, ["auth:key", "revoke", "ci"])
    assert revoked.exit_code == 0, revoked.output

    missing = runner.invoke(cli_app, ["auth:key", "revoke", "ci"])
    assert missing.exit_code == 1

    who = runner.invoke(cli_app, ["auth:whoami"])
    assert who.exit_code == 0
    assert "owner_id:" in who.output
    get_settings.cache_clear()


def test_a2a_task_type_helper_still_importable():
    assert t.Task is not None
