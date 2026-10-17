"""WS0 — foundation primitives: collection, casts, pagination, signature, gate, rules."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentkit import (
    App,
    Collection,
    CursorCollection,
    GateManager,
    LengthAwarePaginator,
    Policy,
    Rule,
    Signature,
    ValidationRule,
    Validator,
    build_click_command,
    collect,
    parse_signature,
    resolve_cast,
)
from agentkit.errors import PermissionDenied
from agentkit.foundation import discovery
from agentkit.foundation.events import ShouldBroadcast, ShouldQueue, should_broadcast, should_queue
from agentkit.foundation.validation import set_uniqueness_resolver


# -- Collection -------------------------------------------------------------
def test_collection_transforms() -> None:
    items = collect([1, 2, 3, 4])
    assert items.map(lambda n: n * 2).all() == [2, 4, 6, 8]
    assert items.filter(lambda n: n % 2 == 0).all() == [2, 4]
    assert items.reject(lambda n: n % 2 == 0).all() == [1, 3]
    assert items.take(2).all() == [1, 2]
    assert items.skip(1).all() == [2, 3, 4]
    assert items.reverse().all() == [4, 3, 2, 1]
    assert items.chunk(2).map(lambda c: c.all()).all() == [[1, 2], [3, 4]]
    assert items.count() == 4
    assert items.sum() == 10
    assert items.avg() == 2.5
    assert items.min() == 1 and items.max() == 4
    assert items.implode(",") == "1,2,3,4"


def test_collection_pluck_group_keyby_unique() -> None:
    rows = collect(
        [
            {"name": "a", "kind": "x"},
            {"name": "b", "kind": "x"},
            {"name": "c", "kind": "y"},
        ]
    )
    assert rows.pluck("name").all() == ["a", "b", "c"]
    grouped = rows.groupBy("kind")
    assert grouped["x"].pluck("name").all() == ["a", "b"]
    assert rows.keyBy("name")["b"] == {"name": "b", "kind": "x"}
    assert collect([1, 1, 2]).unique().all() == [1, 2]
    assert rows.first()["name"] == "a"
    assert rows.last()["name"] == "c"
    assert rows.contains(lambda row: row["name"] == "c")
    assert rows.reduce(lambda total, row: total + row["name"], "") == "abc"


def test_collection_attributes_and_eq() -> None:
    items = collect([3, 1, 2])
    assert items.sortBy().all() == [1, 2, 3]
    assert items.sortBy(descending=True).all() == [3, 2, 1]
    assert items.isNotEmpty() and not items.isEmpty()
    assert items.to_list() == [3, 1, 2]
    assert items == [3, 1, 2]
    assert list(items) == [3, 1, 2]
    assert len(items) == 3
    assert items[0] == 3
    assert items[0:2].all() == [3, 1]
    assert items.merge([9]).all() == [3, 1, 2, 9]
    assert items.push(4).all() == [3, 1, 2, 4]
    assert items[10:20].isEmpty()
    assert Collection() == []
    assert collect(items) is items


def test_cursor_collection_lazy() -> None:
    seen: list[int] = []

    def source():
        for index in range(10):
            seen.append(index)
            yield index

    cursor = CursorCollection(source()).map(lambda n: n * 2).filter(lambda n: n % 4 == 0)
    assert seen == []  # lazy until consumed
    assert cursor.take(2).to_list() == [0, 4]
    assert CursorCollection([1, 2, 3]).each(lambda n: n).to_list() == [1, 2, 3]


# -- Casts ------------------------------------------------------------------
def test_cast_roundtrip() -> None:
    assert resolve_cast("int").get(None, "x", "5") == 5
    assert resolve_cast("integer").set(None, "x", "5") == 5
    assert resolve_cast("float").get(None, "x", "1.5") == 1.5
    assert resolve_cast("bool").get(None, "x", 0) is False
    assert resolve_cast("bool").set(None, "x", "yes") is True
    assert resolve_cast("bool").set(None, "x", "no") is False
    assert resolve_cast("json").get(None, "x", '{"a": 1}') == {"a": 1}
    assert resolve_cast("json").set(None, "x", {"a": 1}) == '{"a": 1}'
    assert resolve_cast("array").get(None, "x", None) == []
    assert resolve_cast("collection").get(None, "x", "[1, 2]").all() == [1, 2]


def test_cast_datetime_and_date() -> None:
    dt = resolve_cast("datetime").get(None, "x", "2030-01-01T09:00:00")
    assert isinstance(dt, datetime) and dt.hour == 9
    assert resolve_cast("datetime").serialize(None, "x", dt) == "2030-01-01T09:00:00"
    stored = resolve_cast("datetime").set(None, "x", "2030-01-01T09:00:00")
    assert stored.replace(tzinfo=None) == dt
    parsed = resolve_cast("date").get(None, "x", "2030-01-01")
    assert parsed == date(2030, 1, 1)
    assert resolve_cast("datetime:Y-m-d").set(None, "x", dt) == "2030-01-01"


def test_resolve_cast_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        resolve_cast("nope")


# -- Pagination -------------------------------------------------------------
def test_paginator() -> None:
    simple = LengthAwarePaginator(items=[1, 2, 3], total=10, per_page=3, current_page=2)
    assert simple.pages == 4
    assert simple.last_page == 4
    assert simple.from_ == 4 and simple.to == 6
    assert simple.has_more_pages() is True
    assert simple.on_first_page() is False
    assert simple.links()["next"] == "3"
    assert simple.links()["prev"] == "1"
    assert simple["total"] == 10 and simple["page"] == 2 and simple["items"] == [1, 2, 3]
    assert len(simple) == 3
    assert simple.to_dict()["pages"] == 4


def test_paginator_empty_and_last_page() -> None:
    empty = LengthAwarePaginator(items=[], total=0)
    assert empty.pages == 0 and empty.last_page == 1
    assert empty.from_ == 0 and empty.to == 0
    assert empty.has_more_pages() is False
    final = LengthAwarePaginator(items=[9], total=4, per_page=3, current_page=2)
    assert final.on_last_page() is True
    assert final.links()["next"] is None


# -- Signature --------------------------------------------------------------
def test_parse_signature_grammar() -> None:
    sig = parse_signature("make:model {name} {optional?} {tags*} {--force} {--F|full} {--o|owner=}")
    assert sig.name == "make:model"
    assert [(a.name, a.required, a.variadic) for a in sig.arguments] == [
        ("name", True, False),
        ("optional", False, False),
        ("tags", True, True),
    ]
    assert sig.option("force").takes_value is False
    assert sig.option("full").shortcut == "F"
    owner = sig.option("owner")
    assert owner.takes_value is True and owner.shortcut == "o"
    assert Signature.parse("x {name=dflt}").argument("name").default == "dflt"


def test_build_click_command_runs_handler() -> None:
    captured: dict[str, object] = {}

    def handler(parsed):  # noqa: ANN001
        captured["args"] = parsed.arguments
        captured["opts"] = parsed.options
        return "done"

    command = build_click_command(
        "greet {name} {--loud} {--count=}", handler, help="greet someone"
    )
    result = CliRunner().invoke(command, ["Ada", "--loud", "--count", "3"])
    assert result.exit_code == 0, result.output
    assert captured["args"] == {"name": "Ada"}
    assert captured["opts"] == {"loud": True, "count": "3"}


def test_build_click_command_variadic() -> None:
    captured: dict[str, object] = {}

    def handler(parsed):  # noqa: ANN001
        captured.update(parsed.arguments)

    command = build_click_command("tag {names*}", handler)
    result = CliRunner().invoke(command, ["a", "b", "c"])
    assert result.exit_code == 0
    assert captured == {"names": ("a", "b", "c")}


# -- Validation rules -------------------------------------------------------
def test_validation_rule_objects() -> None:
    class Even(ValidationRule):
        def validate(self, attribute, value, fail):  # noqa: ANN001
            if value % 2 != 0:
                fail("must be even")

    data = {"n": 4}
    assert Validator(data, {"n": [Even(), "integer"]}).validate() == {"n": 4}
    validator = Validator({"n": 3}, {"n": [Even()]})
    assert validator.fails() is True
    assert validator.first("n") == "the n field must be even"


def test_rule_object_factory_and_string_sugar() -> None:
    assert Validator({"kind": "x"}, {"kind": [Rule.in_("x", "y")]}).passes() is True
    assert Validator({"kind": "z"}, {"kind": [Rule.in_("x", "y")]}).fails() is True
    # strings stay sugar (existing behaviour intact)
    assert Validator({"text": "stretch"}, {"text": ["required", "min:3"]}).passes()
    assert Validator({"text": ""}, {"text": ["required"]}).first("text") == (
        "the text field is required"
    )


def test_unique_and_exists_rules_use_resolver() -> None:
    calls: list[tuple[type, dict]] = []

    def resolver(model, filters):  # noqa: ANN001
        calls.append((model, filters))
        return filters.get("name") == "taken"

    set_uniqueness_resolver(resolver)
    try:
        assert Validator({"name": "free"}, {"name": [Rule.unique(dict, "name")]}).passes()
        assert Validator({"name": "taken"}, {"name": [Rule.unique(dict, "name")]}).fails()
        assert Validator({"name": "taken"}, {"name": [Rule.exists(dict, "name")]}).passes()
        assert Validator({"name": "free"}, {"name": [Rule.exists(dict, "name")]}).fails()
    finally:
        set_uniqueness_resolver(None)
    assert calls


def test_unique_rule_without_resolver_raises() -> None:
    with pytest.raises(RuntimeError):
        Validator({"name": "x"}, {"name": [Rule.unique(dict, "name")]}).validate()


# -- Events markers ---------------------------------------------------------
def test_should_queue_and_broadcast_markers() -> None:
    class Queued(ShouldQueue):
        pass

    class Broadcast(ShouldBroadcast):
        pass

    assert should_queue(Queued()) and not should_queue(object())
    assert should_broadcast(Broadcast()) and not should_broadcast(object())


# -- Gate -------------------------------------------------------------------
class _Note:
    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id


class _Actor:
    def __init__(self, ident: str) -> None:
        self.id = ident


class _NotePolicy(Policy):
    model = _Note

    def view(self, actor, note):  # noqa: ANN001
        return note.owner_id == actor.id

    def update(self, actor, note):  # noqa: ANN001
        return note.owner_id == actor.id

    def create(self, actor, note=None):  # noqa: ANN001
        return True


def test_gate_policy_resolution() -> None:
    gate = GateManager()
    gate.policy(_Note, _NotePolicy)
    actor = _Actor("ada")
    assert gate.allows("view", _Note("ada"), actor=actor) is True
    assert gate.denies("view", _Note("bob"), actor=actor) is True
    assert gate.allows("create", _Note, actor=actor) is True
    with pytest.raises(PermissionDenied):
        gate.authorize("update", _Note("bob"), actor=actor)


def test_gate_define_and_undefined_ability() -> None:
    gate = GateManager()
    gate.define("publish", lambda actor, subject: actor.id == "ada")
    actor = _Actor("ada")
    assert gate.allows("publish", object(), actor=actor) is True
    assert gate.denies("unmapped", object(), actor=actor) is True
    assert gate.has("publish") and not gate.has("unmapped")


def test_gate_for_user_and_before_hook() -> None:
    gate = GateManager()
    gate.before(lambda actor, ability, subject: True if ability == "super" else None)
    inspector = gate.for_user(_Actor("ada"))
    assert inspector.can("super", object()) is True
    assert inspector.cannot("view", object()) is True
    assert inspector.any(["view", "super"], object()) is True


def test_gate_response_inspect() -> None:
    gate = GateManager()
    gate.define("read", lambda actor, subject: False)
    response = gate.inspect("read", None, actor=_Actor("ada"))
    assert response.allowed is False and response.message is None
    missing = gate.inspect("nope", None, actor=_Actor("ada"))
    assert missing.allowed is False and "nope" in (missing.message or "")


def test_app_gate_facade(runtime) -> None:  # noqa: ANN001
    from agentkit import Gate as GateFacade

    app = App(name="gate", settings=runtime.settings, discover=False)
    app.boot()
    app.gate.define("ping", lambda actor, subject: True)
    assert GateFacade.allows("ping", None) is True
    assert app.gate is app.make("gate")


# -- Policy discovery -------------------------------------------------------
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _policy_project(root: Path) -> Path:
    _write(root / "app" / "__init__.py", "")
    _write(root / "app" / "Policies" / "__init__.py", "")
    _write(
        root / "app" / "Policies" / "NotePolicy.py",
        "from agentkit import Policy\n\n\n"
        "class NotePolicy(Policy):\n    model = dict\n",
    )
    return root


def test_discover_policies(tmp_path: Path) -> None:
    root = _policy_project(tmp_path / "proj")
    resolved = str(root.resolve())
    try:
        found = discovery.discover_policies(root)
        assert [p.__name__ for p in found] == ["NotePolicy"]
    finally:
        sys.path[:] = [entry for entry in sys.path if entry != resolved]
        for name, module in list(sys.modules.items()):
            source = getattr(module, "__file__", None)
            if source and resolved in source:
                sys.modules.pop(name, None)
