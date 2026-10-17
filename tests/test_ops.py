from __future__ import annotations

import asyncio

from click.testing import CliRunner
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from agentkit import metrics
from agentkit.cli import app as cli_app
from agentkit.config import AgentSettings, get_settings
from agentkit.db.engine import async_database_url, create_async_db_engine
from agentkit.health import db_check, readiness_checks, run_checks
from agentkit.runtime import build_runtime
from agentkit.webui.app import build_webui_app


def test_metrics_render_and_gate(tmp_path):
    settings = AgentSettings(owner_id="o", agent_home=tmp_path, memory_embedding_backend="hash")
    runtime = build_runtime(settings)
    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    # disabled by default: the SPA fallback serves HTML, not Prometheus text
    assert "agentkit_turns_total" not in client.get("/metrics").text

    settings.metrics_enabled = True
    metrics.enable(settings)
    metrics.record_turn("ok", 0.01)
    metrics.record_tool_error("db_find")
    metrics.record_queue_depth("default", 2)
    metrics.record_scheduler_run("x", "ok")
    metrics.record_cost(0.25)

    client = TestClient(build_webui_app(runtime=runtime, settings=settings))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "agentkit_turns_total" in response.text
    assert "agentkit_cost_usd_total" in response.text


def test_postgres_url_mapping():
    assert async_database_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert async_database_url("postgres://u@h/db") == "postgresql+asyncpg://u@h/db"
    assert async_database_url("sqlite:///x.db") == "sqlite+aiosqlite:///x.db"


def test_create_postgres_engine_without_connecting():
    engine = create_async_db_engine("postgresql://u:p@localhost:5432/db")
    assert engine.dialect.name == "postgresql"
    asyncio.run(engine.dispose())


async def test_readiness_checks_are_dependency_aware(tmp_path):
    key = Fernet.generate_key().decode()
    settings = AgentSettings(
        owner_id="o",
        agent_home=tmp_path,
        memory_embedding_backend="hash",
        queue_enabled=True,
        credentials_enabled=True,
        credentials_key=key,
    )
    runtime = build_runtime(settings)
    names = {check.name for check in readiness_checks(runtime, settings)}
    assert {"db", "queue", "vault"} <= names

    ok, results = await run_checks([db_check(runtime)])
    assert ok is True and results["db"] is True


def test_cli_migrate_backup_health(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMORY_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()
    runner = CliRunner()

    migrated = runner.invoke(cli_app, ["migrate"])
    assert migrated.exit_code == 0, migrated.output
    assert (tmp_path / "home" / "agent.db").is_file()

    backup = runner.invoke(cli_app, ["db:backup"])
    assert backup.exit_code == 0, backup.output
    assert (tmp_path / "home" / "agent.db.bak").is_file()

    restored = runner.invoke(cli_app, ["db:restore", str(tmp_path / "home" / "agent.db.bak"), "--yes"])
    assert restored.exit_code == 0, restored.output

    health = runner.invoke(cli_app, ["health"])
    assert health.exit_code == 0, health.output
    assert "db: ok" in health.output
    get_settings.cache_clear()
