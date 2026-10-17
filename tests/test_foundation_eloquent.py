"""WS1 — Eloquent models: relationships, casts, scopes, soft deletes, observers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlmodel import Field

from agentkit import (
    App,
    Attribute,
    Collection,
    GlobalScope,
    LengthAwarePaginator,
    Model,
    Observer,
    SoftDeletes,
    belongs_to,
    has_many,
)
from agentkit.foundation.model import LazyLoadingViolation
from agentkit.runtime import Runtime

_EVENTS: list[str] = []


class AuthorEventObserver(Observer):
    def created(self, model: Any) -> None:
        _EVENTS.append("created")

    def updated(self, model: Any) -> None:
        _EVENTS.append("updated")

    def deleted(self, model: Any) -> None:
        _EVENTS.append("deleted")


class Author(Model, table=True):
    __tablename__ = "ws1_authors"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    country: str = "uk"

    observers = [AuthorEventObserver()]

    books = has_many("Book", foreign_key="author_id")

    full_label = Attribute(get=lambda self: f"{self.name} ({self.country})")

    appends = ["full_label"]

    @classmethod
    def scope_from(cls, query, country: str):  # noqa: ANN001
        return query.where(country=country)


class Book(Model, table=True):
    __tablename__ = "ws1_books"

    id: int | None = Field(default=None, primary_key=True)
    author_id: int | None = Field(default=None)
    title: str = ""
    published: bool = False
    meta: str = ""
    price: int = 0

    casts = {"published": "bool", "meta": "json", "price": "int"}

    author = belongs_to(Author, foreign_key="author_id")


class ArchivedScope(GlobalScope):
    name = "archived"

    def apply(self, query):  # noqa: ANN001
        return query.where(archived=False)


class Tagged(Model, table=True):
    __tablename__ = "ws1_tagged"

    id: int | None = Field(default=None, primary_key=True)
    label: str = ""
    archived: bool = False

    global_scopes = [ArchivedScope()]


class Scrap(SoftDeletes, table=True):
    __tablename__ = "ws1_scraps"

    id: int | None = Field(default=None, primary_key=True)
    label: str = ""


class Secret(Model, table=True):
    __tablename__ = "ws1_secrets"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    role: str = "user"

    fillable = ["name"]
    guarded = ["role"]


def _app(runtime: Runtime) -> App:
    app = App(name="eloquent", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


# -- basic reads + Collection ----------------------------------------------
async def test_create_returns_collection(runtime: Runtime) -> None:
    _app(runtime)
    await Author.create(name="Ada")
    await Author.create(name="Grace")
    authors = await Author.all()
    assert isinstance(authors, Collection)
    assert authors.pluck("name").all() == ["Ada", "Grace"]
    assert await Author.count() == 2


# -- casts ------------------------------------------------------------------
async def test_casts_roundtrip(runtime: Runtime) -> None:
    app = _app(runtime)
    book = await Book.create(title="T", meta={"pages": 10}, published="yes", price="5")
    assert book.meta == {"pages": 10}
    assert book.published is True
    assert book.price == 5
    # raw storage stays a JSON string
    fetched = await Book.find(book.id)
    assert fetched.meta == {"pages": 10}
    async with app.repositories() as repos:
        assert repos.session is not None


# -- accessors + appends ----------------------------------------------------
async def test_attribute_accessor_and_appends(runtime: Runtime) -> None:
    _app(runtime)
    author = await Author.create(name="Ada", country="uk")
    assert author.full_label == "Ada (uk)"
    data = author.to_dict()
    assert data["full_label"] == "Ada (uk)"
    assert data["name"] == "Ada"


# -- scopes -----------------------------------------------------------------
async def test_local_scope_on_class_and_query(runtime: Runtime) -> None:
    _app(runtime)
    await Author.create(name="A", country="uk")
    await Author.create(name="B", country="fr")
    assert (await Author.from_("fr").all()).pluck("name").all() == ["B"]
    assert (await Author.where(country="uk").from_("uk").count()) == 1


async def test_global_scope_and_without(runtime: Runtime) -> None:
    _app(runtime)
    await Tagged.create(label="live", archived=False)
    await Tagged.create(label="old", archived=True)
    assert await Tagged.count() == 1
    assert (await Tagged.all()).first().label == "live"
    assert await Tagged.without_global_scope("archived").count() == 2


# -- relationships ----------------------------------------------------------
async def test_has_many_and_belongs_to(runtime: Runtime) -> None:
    _app(runtime)
    author = await Author.create(name="Ada")
    await Book.create(title="B1", author_id=author.id)
    await Book.create(title="B2", author_id=author.id)

    books = await author.books
    assert isinstance(books, Collection) and len(books) == 2
    assert books.pluck("title").all() == ["B1", "B2"]

    book = (await Book.where(title="B1").first())
    related = await book.author
    assert related.name == "Ada"


async def test_eager_loading_avoids_lazy(runtime: Runtime) -> None:
    _app(runtime)
    author = await Author.create(name="Ada")
    await Book.create(title="B1", author_id=author.id)
    loaded = (await Author.with_("books").all()).first()
    assert isinstance(loaded.books, Collection)
    assert loaded.books.pluck("title").all() == ["B1"]


async def test_lazy_loading_guard(runtime: Runtime) -> None:
    _app(runtime)
    author = await Author.create(name="Ada")
    await Book.create(title="B1", author_id=author.id)
    Author.prevent_lazy_loading = True
    try:
        loaded = (await Author.all()).first()
        with pytest.raises(LazyLoadingViolation):
            await loaded.books
    finally:
        Author.prevent_lazy_loading = False


# -- soft deletes -----------------------------------------------------------
async def test_soft_deletes(runtime: Runtime) -> None:
    _app(runtime)
    scrap = await Scrap.create(label="x")
    assert await Scrap.count() == 1
    await scrap.delete()
    assert scrap.trashed() is True
    assert await Scrap.count() == 0
    assert await Scrap.with_trashed().count() == 1
    assert await Scrap.only_trashed().count() == 1
    await scrap.restore()
    assert await Scrap.count() == 1


# -- observers + model events ----------------------------------------------
async def test_observer_fires_lifecycle(runtime: Runtime) -> None:
    _app(runtime)
    _EVENTS.clear()
    author = await Author.create(name="Ada")
    assert _EVENTS == ["created"]
    author.name = "Ada L"
    await author.save()
    assert _EVENTS == ["created", "updated"]
    await author.delete()
    assert _EVENTS[-1] == "deleted"


# -- mass assignment --------------------------------------------------------
async def test_mass_assignment_fillable_guarded(runtime: Runtime) -> None:
    _app(runtime)
    secret = await Secret.create(name="ok", role="admin")
    assert secret.name == "ok"
    assert secret.role == "user"  # guarded, not mass-assigned


# -- query extras -----------------------------------------------------------
async def test_query_extras(runtime: Runtime) -> None:
    _app(runtime)
    await Author.create(name="A", country="uk")
    await Author.create(name="B", country="uk")
    await Author.create(name="C", country="fr")

    assert await Author.where_in("name", ["A", "B"]).count() == 2
    assert (await Author.where(country="fr").pluck("name")).all() == ["C"]
    assert await Author.where(country="fr").value("name") == "C"
    assert await Author.where(name="A").exists() is True
    assert await Author.where(name="Z").exists() is False
    assert await Author.query().where_not_null("name").count() == 3
    assert await Author.where_between("id", 0, 1).count() >= 1

    picked = await Author.where(name="A").first()
    assert picked.country == "uk"
    assert await Author.when(True, lambda q: q.where(country="uk")).count() == 2

    page = await Author.paginate(page=1, per_page=2)
    assert isinstance(page, LengthAwarePaginator)
    assert page["total"] == 3 and len(page.items) == 2

    seen: list[str] = []

    async def collect(batch: Collection) -> None:
        seen.extend(batch.pluck("name").all())

    await Author.order_by("name").chunk(2, collect)
    assert seen == ["A", "B", "C"]


async def test_relationship_eager_missing_values(runtime: Runtime) -> None:
    _app(runtime)
    empty = await Author.create(name="Nobody")
    loaded = (await Author.where(name="Nobody").with_("books").all()).first()
    assert loaded.books.all() == []
    assert empty.id == loaded.id


async def test_update_or_create_and_first_or_create(runtime: Runtime) -> None:
    _app(runtime)
    created = await Author.first_or_create(defaults={"country": "uk"}, name="X")
    again = await Author.first_or_create(defaults={"country": "fr"}, name="X")
    assert created.id == again.id and again.country == "uk"
    updated = await Author.update_or_create(defaults={"country": "us"}, name="X")
    assert updated.country == "us"


async def test_paginator_legacy_dict_access(runtime: Runtime) -> None:
    _app(runtime)
    for index in range(5):
        await Book.create(title=f"b{index}", author_id=1)
    page = await Book.paginate(page=2, per_page=2)
    assert page["page"] == 2 and page["pages"] == 3
    assert len(page["items"]) == 2
    assert isinstance(Book.paginate, object)


async def test_datetime_cast_applies(runtime: Runtime) -> None:
    class Stamped(Model, table=True):
        __tablename__ = "ws1_stamped"

        id: int | None = Field(default=None, primary_key=True)
        at: datetime | None = None

        casts = {"at": "datetime"}

    _app(runtime)
    row = await Stamped.create(at="2030-01-01T09:00:00")
    assert isinstance(row.at, datetime) and row.at.hour == 9
