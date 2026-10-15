from __future__ import annotations

from sqlmodel import Field

from agentkit import DB, App, Model
from agentkit.runtime import Runtime


class Note(Model, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    tag: str = "misc"


def _app(runtime: Runtime) -> App:
    app = App(name="model", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


async def test_model_crud(runtime: Runtime):
    _app(runtime)
    created = await Note.create(text="hello", tag="a")
    assert created.id is not None

    row = await Note.where(text="hello").first()
    assert row is not None and row.text == "hello"
    got = await Note.get(created.id)
    assert got is not None and got.text == "hello"
    assert await Note.query(tag="a").count() == 1
    assert await Note.count() == 1

    updated = await Note.update(created.id, text="hi")
    assert updated is not None and updated.text == "hi"
    refreshed = await Note.get(created.id)
    assert refreshed is not None and refreshed.text == "hi"

    assert await Note.delete(created.id) is True
    assert await Note.delete(created.id) is False
    assert await Note.count() == 0


async def test_model_where_chains_and_order(runtime: Runtime):
    _app(runtime)
    await Note.create(text="b", tag="x")
    await Note.create(text="a", tag="x")
    await Note.create(text="c", tag="y")
    rows = await Note.where(tag="x").order_by("text").all()
    assert [row.text for row in rows] == ["a", "b"]
    assert await Note.where(tag="x").count() == 2


async def test_model_paginate(runtime: Runtime):
    _app(runtime)
    for index in range(5):
        await Note.create(text=f"n{index}", tag="p")
    page = await Note.paginate(page=2, per_page=2, tag="p")
    assert page["total"] == 5
    assert page["pages"] == 3
    assert len(page["items"]) == 2
    assert page["page"] == 2


async def test_db_transaction_makes_session_ambient(runtime: Runtime):
    app = _app(runtime)
    assert app.db is not None
    async with DB.transaction():
        await Note.create(text="a")
        await Note.create(text="b")
    assert await Note.count() == 2


async def test_model_get_missing_returns_none(runtime: Runtime):
    _app(runtime)
    assert await Note.get(9999) is None
    assert await Note.update(9999, text="x") is None
    assert await Note.where(text="nope").first() is None
