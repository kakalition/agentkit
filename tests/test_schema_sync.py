from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from agentkit.db.migrations import init_db, sync_missing_columns


def _engine(tmp_path, name: str):
    return create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")


async def test_sync_missing_columns_adds_drifted_column(tmp_path):
    engine = _engine(tmp_path, "drift.db")
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE a2a_tasks (id VARCHAR PRIMARY KEY, state VARCHAR NOT NULL)")
        )

    added = await sync_missing_columns(engine)

    async with engine.connect() as conn:
        columns = {column["name"] for column in await conn.run_sync(
            lambda c: inspect(c).get_columns("a2a_tasks")
        )}
    assert "owner_id" in columns
    assert "a2a_tasks.owner_id" in added


async def test_sync_missing_columns_is_idempotent(tmp_path):
    engine = _engine(tmp_path, "idempotent.db")
    await init_db(engine)
    assert await sync_missing_columns(engine) == []


async def test_memory_upgrade_adds_typed_columns_and_profile(tmp_path):
    """An old ``memories`` table gains the typed columns and OwnerProfile appears."""
    engine = _engine(tmp_path, "upgrade.db")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE memories ("
                "id INTEGER PRIMARY KEY, owner_id VARCHAR NOT NULL, kind VARCHAR, "
                "content VARCHAR NOT NULL, embedding VARCHAR, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO memories (owner_id, kind, content) VALUES ('owner', 'fact', 'old fact')"
            )
        )

    await init_db(engine)

    async with engine.connect() as conn:
        columns = {column["name"] for column in await conn.run_sync(
            lambda c: inspect(c).get_columns("memories")
        )}
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
    assert {
        "importance",
        "last_used_at",
        "access_count",
        "source_conversation_id",
        "expires_at",
    } <= columns
    assert "owner_profile" in tables

    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT kind, importance, access_count FROM memories"))
        ).one()
    assert row.kind == "fact"
    assert row.importance == 0.5
    assert row.access_count == 0
