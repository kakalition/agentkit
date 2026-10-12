from __future__ import annotations

from sqlmodel import Field, SQLModel

from agentkit import DB, App, Model
from agentkit.runtime import Runtime


class Note(Model, table=True):
    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    tag: str = "misc"


def _app(runtime: Runtime) -> App:
    SQLModel.metadata.create_all(runtime.engine)
    app = App(name="model", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


def test_model_crud(runtime: Runtime):
    _app(runtime)
    created = Note.create(text="hello", tag="a")
    assert created.id is not None

    assert Note.where(text="hello").first().text == "hello"
    assert Note.get(created.id).text == "hello"
    assert Note.query(tag="a").count() == 1
    assert Note.count() == 1

    updated = Note.update(created.id, text="hi")
    assert updated.text == "hi"
    assert Note.get(created.id).text == "hi"

    assert Note.delete(created.id) is True
    assert Note.delete(created.id) is False
    assert Note.count() == 0


def test_model_where_chains_and_order(runtime: Runtime):
    _app(runtime)
    Note.create(text="b", tag="x")
    Note.create(text="a", tag="x")
    Note.create(text="c", tag="y")
    rows = Note.where(tag="x").order_by("text").all()
    assert [row.text for row in rows] == ["a", "b"]
    assert Note.where(tag="x").count() == 2


def test_model_paginate(runtime: Runtime):
    _app(runtime)
    for index in range(5):
        Note.create(text=f"n{index}", tag="p")
    page = Note.paginate(page=2, per_page=2, tag="p")
    assert page["total"] == 5
    assert page["pages"] == 3
    assert len(page["items"]) == 2
    assert page["page"] == 2


def test_db_transaction_makes_session_ambient(runtime: Runtime):
    app = _app(runtime)
    assert app.db is not None
    with DB.transaction():
        Note.create(text="a")
        Note.create(text="b")
    assert Note.count() == 2


def test_model_get_missing_returns_none(runtime: Runtime):
    _app(runtime)
    assert Note.get(9999) is None
    assert Note.update(9999, text="x") is None
    assert Note.where(text="nope").first() is None
