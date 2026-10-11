from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from agentkit.db.migrations import sync_missing_columns


def test_sync_missing_columns_adds_drifted_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE a2a_tasks (id VARCHAR PRIMARY KEY, state VARCHAR NOT NULL)")
        )

    added = sync_missing_columns(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("a2a_tasks")}
    assert "owner_id" in columns
    assert "a2a_tasks.owner_id" in added


def test_sync_missing_columns_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'idempotent.db'}")
    from agentkit.db.migrations import init_db

    init_db(engine)
    assert sync_missing_columns(engine) == []
