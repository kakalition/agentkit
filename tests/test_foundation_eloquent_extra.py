"""WS1 (cont.) — factories, seeders, migrations, ambient-session relationships."""

from __future__ import annotations

from typing import Any

from sqlmodel import Field

from agentkit import (
    DB,
    App,
    Collection,
    Factory,
    HasFactory,
    Migration,
    Migrator,
    Model,
    Schema,
    Seeder,
    SeederRunner,
    belongs_to,
    has_many,
)
from agentkit.foundation.relations import primary_key_name
from agentkit.runtime import Runtime


class Widget(Model, HasFactory, table=True):
    __tablename__ = "ws1_widgets"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    kind: str = "basic"


class WidgetFactory(Factory):
    model = Widget

    def definition(self) -> dict[str, Any]:
        return {"name": "widget", "kind": "basic"}


class Team(Model, table=True):
    __tablename__ = "ws1_teams"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""

    members = has_many("Member", foreign_key="team_id")


class Member(Model, table=True):
    __tablename__ = "ws1_members"

    id: int | None = Field(default=None, primary_key=True)
    team_id: int | None = Field(default=None)
    name: str = ""

    team = belongs_to(Team, foreign_key="team_id")


def _app(runtime: Runtime) -> App:
    app = App(name="ws1extra", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


# -- factories --------------------------------------------------------------
async def test_factory_make_and_create(runtime: Runtime) -> None:
    _app(runtime)
    instance = Widget.factory().make()
    assert isinstance(instance, Widget) and instance.name == "widget"
    assert await Widget.count() == 0  # make does not persist

    created = await Widget.factory().create(name="custom")
    assert created.id is not None and created.name == "custom"
    assert await Widget.count() == 1


async def test_factory_count_and_state(runtime: Runtime) -> None:
    _app(runtime)
    made = await Widget.factory(count=3).state({"kind": "pro"}).create()
    assert isinstance(made, Collection) and len(made) == 3
    assert made.pluck("kind").unique().all() == ["pro"]

    many = Widget.factory().make_many(2)
    assert len(many) == 2


async def test_factory_registry_and_after_creating(runtime: Runtime) -> None:
    _app(runtime)
    seen: list[int] = []

    class Tag(Model, table=True):
        __tablename__ = "ws1_tags"

        id: int | None = Field(default=None, primary_key=True)
        label: str = ""

    class TagFactory(Factory):
        model = Tag

        def definition(self) -> dict[str, Any]:
            return {"label": "t"}

    Factory.for_model(Tag, TagFactory)
    track = TagFactory().after_creating(lambda instance: seen.append(instance.id))
    created = await track.create()
    assert seen == [created.id]


# -- seeders ----------------------------------------------------------------
async def test_seeder_runner(runtime: Runtime) -> None:
    _app(runtime)

    class WidgetSeeder(Seeder):
        async def run(self) -> None:
            await Widget.create(name="seeded")

    class SyncSeeder(Seeder):
        def run(self) -> None:
            return None

    await SeederRunner([WidgetSeeder, SyncSeeder]).run()
    assert await Widget.where(name="seeded").count() == 1


# -- migrations -------------------------------------------------------------
class CreateWidgetsTable(Migration):
    name = "0001_create_widgets_table"

    def up(self, schema: Schema) -> None:
        schema.create("ws1_migrated", lambda t: (t.id(), t.string("name"), t.timestamps()))

    def down(self, schema: Schema) -> None:
        schema.drop("ws1_migrated")


class AddFlagColumn(Migration):
    name = "0002_add_flag_column"

    def up(self, schema: Schema) -> None:
        schema.table("ws1_migrated", lambda t: t.boolean("flag", nullable=False, default=False))

    def down(self, schema: Schema) -> None:
        return None


async def test_migrator_up_and_rollback(runtime: Runtime) -> None:
    migrator = Migrator(runtime.engine, [CreateWidgetsTable, AddFlagColumn])

    executed = await migrator.migrate()
    assert executed == ["0001_create_widgets_table", "0002_add_flag_column"]
    status = await migrator.status()
    assert all(ran for _, ran, _ in status)

    async with runtime.engine.begin() as connection:
        tables = await connection.run_sync(lambda conn: Schema(conn).has_table("ws1_migrated"))
    assert tables is True

    rolled = await migrator.rollback()
    assert set(rolled) == {"0001_create_widgets_table", "0002_add_flag_column"}

    async with runtime.engine.begin() as connection:
        assert await connection.run_sync(lambda conn: Schema(conn).has_table("ws1_migrated")) is False


async def test_migrator_is_idempotent(runtime: Runtime) -> None:
    migrator = Migrator(runtime.engine, [CreateWidgetsTable])
    assert await migrator.migrate() == ["0001_create_widgets_table"]
    assert await migrator.migrate() == []


# -- ambient session + relationships ---------------------------------------
async def test_relationship_inside_transaction(runtime: Runtime) -> None:
    _app(runtime)
    async with DB.transaction():
        team = await Team.create(name="core")
        await Member.create(team_id=team.id, name="Ada")
        await Member.create(team_id=team.id, name="Grace")
        members = await team.members
        assert isinstance(members, Collection)
        assert members.pluck("name").all() == ["Ada", "Grace"]

    assert await Member.count() == 2
    assert primary_key_name(Team) == "id"
