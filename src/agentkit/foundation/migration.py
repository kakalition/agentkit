"""Class-based migrations (Laravel's ``Migration`` + ``Schema``).

    class CreateNotesTable(Migration):
        def up(self, schema):
            schema.create("notes", lambda t: (t.id(), t.string("text")))

        def down(self, schema):
            schema.drop("notes")

Migrations are additive over the existing ``init_db`` auto-create: they run only
when an app declares them (``app.migrations([...])`` or ``database/migrations/``).
The batch numbers are recorded in a ``migrations(name, batch, ran_at)`` table.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
)

from agentkit.foundation.clock import now

__all__ = [
    "Blueprint",
    "Migration",
    "MigrationRepository",
    "Migrator",
    "Schema",
    "discover_migrations",
]


class Blueprint:
    """Collects columns/constraints for a new or altered table."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._columns: list[Column] = []
        self._constraints: list[Any] = []
        self._indexes: list[Index] = []

    # -- column helpers -------------------------------------------------
    def id(self, name: str = "id") -> Blueprint:
        self._columns.append(Column(name, Integer, primary_key=True, autoincrement=True))
        return self

    def integer(self, name: str, *, nullable: bool = True, default: Any = None) -> Blueprint:
        self._columns.append(Column(name, Integer, nullable=nullable, default=default))
        return self

    def bigint(self, name: str, *, nullable: bool = True, default: Any = None) -> Blueprint:
        self._columns.append(Column(name, Integer, nullable=nullable, default=default))
        return self

    def boolean(self, name: str, *, nullable: bool = True, default: Any = None) -> Blueprint:
        self._columns.append(Column(name, Boolean, nullable=nullable, default=default))
        return self

    def string(
        self, name: str, length: int = 255, *, nullable: bool = True, default: Any = None
    ) -> Blueprint:
        self._columns.append(Column(name, String(length), nullable=nullable, default=default))
        return self

    def text(self, name: str, *, nullable: bool = True) -> Blueprint:
        self._columns.append(Column(name, Text, nullable=nullable))
        return self

    def float(self, name: str, *, nullable: bool = True, default: Any = None) -> Blueprint:
        self._columns.append(Column(name, Float, nullable=nullable, default=default))
        return self

    def datetime(self, name: str, *, nullable: bool = True, default: Any = None) -> Blueprint:
        self._columns.append(Column(name, DateTime, nullable=nullable, default=default))
        return self

    def timestamps(self) -> Blueprint:
        self.datetime("created_at")
        self.datetime("updated_at")
        return self

    def foreign(
        self, name: str, references: str, *, on_delete: str | None = None, nullable: bool = True
    ) -> Blueprint:
        self._columns.append(
            Column(name, Integer, ForeignKey(references, ondelete=on_delete), nullable=nullable)
        )
        return self

    def unique(self, *columns: str, name: str | None = None) -> Blueprint:
        self._constraints.append(UniqueConstraint(*columns, name=name))
        return self

    def index(self, *columns: str, name: str | None = None) -> Blueprint:
        self._indexes.append(Index(name or f"ix_{self.name}_{'_'.join(columns)}", *columns))
        return self

    def raw(self, column: Column) -> Blueprint:
        self._columns.append(column)
        return self

    # -- materialization ------------------------------------------------
    def columns(self) -> list[Column]:
        return list(self._columns)

    def to_table(self, metadata: MetaData | None = None) -> Table:
        meta = metadata or MetaData()
        return Table(self.name, meta, *self._columns, *self._constraints)


class Schema:
    """DDL helpers over a synchronous connection (run inside ``run_sync``)."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(self, name: str, callback: Callable[[Blueprint], Any]) -> Table:
        blueprint = Blueprint(name)
        callback(blueprint)
        table = blueprint.to_table()
        table.create(self.connection)
        for index in blueprint._indexes:  # noqa: SLF001 - internal to the builder
            index.create(self.connection)
        return table

    def table(self, name: str, callback: Callable[[Blueprint], Any]) -> Blueprint:
        """Alter a table (v1: adds the columns the callback declares)."""
        blueprint = Blueprint(name)
        callback(blueprint)
        existing = {column["name"] for column in inspect(self.connection).get_columns(name)}
        for column in blueprint.columns():
            if column.name in existing:
                continue
            ddl = str(
                column.compile(dialect=self.connection.dialect)
            )
            self.connection.exec_driver_sql(f"ALTER TABLE {name} ADD COLUMN {ddl}")
        return blueprint

    def drop(self, name: str) -> None:
        self.connection.exec_driver_sql(f"DROP TABLE {name}")

    def drop_if_exists(self, name: str) -> None:
        self.connection.exec_driver_sql(f"DROP TABLE IF EXISTS {name}")

    def has_table(self, name: str) -> bool:
        return bool(inspect(self.connection).has_table(name))

    def rename(self, name: str, to: str) -> None:
        self.connection.exec_driver_sql(f"ALTER TABLE {name} RENAME TO {to}")


class Migration:
    """Base migration: implement :meth:`up` (and optionally :meth:`down`)."""

    name: str = ""

    def up(self, schema: Schema) -> Any:
        raise NotImplementedError

    def down(self, schema: Schema) -> Any:
        return None

    @classmethod
    def migration_name(cls) -> str:
        return cls.name or cls.__name__


class MigrationRepository:
    """Tracks which migrations have run and in which batch."""

    table_name = "migrations"

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._table = Table(
            self.table_name,
            MetaData(),
            Column("name", String(255), primary_key=True),
            Column("batch", Integer, nullable=False),
            Column("ran_at", DateTime, nullable=False),
        )
        self._table.create(self.connection, checkfirst=True)

    def ran(self) -> list[str]:
        rows = self.connection.execute(self._table.select()).fetchall()
        return [row[0] for row in rows]

    def log(self, name: str, batch: int) -> None:
        self.connection.execute(
            self._table.insert().values(name=name, batch=batch, ran_at=now())
        )

    def delete(self, name: str) -> None:
        self.connection.execute(self._table.delete().where(self._table.c.name == name))

    def last_batch(self) -> int | None:
        rows = self.connection.execute(
            self._table.select().with_only_columns(self._table.c.batch)
        ).fetchall()
        batches = [row[0] for row in rows]
        return max(batches) if batches else None

    def next_batch(self) -> int:
        return (self.last_batch() or 0) + 1

    def batch_migrations(self, batch: int) -> list[str]:
        rows = self.connection.execute(
            self._table.select()
            .where(self._table.c.batch == batch)
            .order_by(self._table.c.name.desc())
        ).fetchall()
        return [row[0] for row in rows]


class Migrator:
    """Runs and rolls back a set of :class:`Migration` classes."""

    def __init__(self, engine: Any, migrations: Sequence[type[Migration]]) -> None:
        self.engine = engine
        self.migrations = [m for m in migrations if isinstance(m, type)]
        self.migrations.sort(key=lambda m: m.migration_name())

    async def migrate(self) -> list[str]:
        async with self.engine.begin() as connection:
            return await connection.run_sync(self._migrate_sync)

    async def rollback(self, steps: int = 1) -> list[str]:
        async with self.engine.begin() as connection:
            return await connection.run_sync(lambda conn: self._rollback_sync(conn, steps))

    async def status(self) -> list[tuple[str, bool, int | None]]:
        async with self.engine.begin() as connection:
            return await connection.run_sync(self._status_sync)

    # -- sync bodies ----------------------------------------------------
    def _migrate_sync(self, connection: Any) -> list[str]:
        repository = MigrationRepository(connection)
        ran = set(repository.ran())
        pending = [m for m in self.migrations if m.migration_name() not in ran]
        if not pending:
            return []
        batch = repository.next_batch()
        executed: list[str] = []
        for migration in pending:
            migration().up(Schema(connection))
            repository.log(migration.migration_name(), batch)
            executed.append(migration.migration_name())
        return executed

    def _rollback_sync(self, connection: Any, steps: int) -> list[str]:
        repository = MigrationRepository(connection)
        rolled: list[str] = []
        by_name = {m.migration_name(): m for m in self.migrations}
        for _ in range(max(1, steps)):
            batch = repository.last_batch()
            if batch is None:
                break
            for name in repository.batch_migrations(batch):
                migration = by_name.get(name)
                if migration is not None:
                    migration().down(Schema(connection))
                repository.delete(name)
                rolled.append(name)
        return rolled

    def _status_sync(self, connection: Any) -> list[tuple[str, bool, int | None]]:
        repository = MigrationRepository(connection)
        rows = {
            row[0]: row[1]
            for row in connection.execute(
                repository._table.select()  # noqa: SLF001 - repository-owned table
            ).fetchall()
        }
        return [
            (migration.migration_name(), migration.migration_name() in rows, rows.get(migration.migration_name()))
            for migration in self.migrations
        ]


def discover_migrations(base_path: str | Path = ".", relative: str = "database/migrations") -> list[type]:
    """Import ``database/migrations/*.py`` and return the ``Migration`` subclasses."""
    root = Path(base_path).expanduser().resolve()
    directory = root / relative
    if not directory.is_dir():
        return []
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    found: list[type] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = ".".join(path.relative_to(root).with_suffix("").parts)
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, Migration)
                and value is not Migration
                and getattr(value, "__module__", None) == module.__name__
            ):
                found.append(value)
    return found
