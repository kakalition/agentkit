from __future__ import annotations

from types import SimpleNamespace

from agentkit.db.models import Feedback
from agentkit.deps import Deps
from agentkit.foundation.agent import Agent
from agentkit.foundation.repository import Repository


class FeedbackRepo(Repository[Feedback]):
    model = Feedback


def _fn(agent, name):
    return agent._function_toolset.tools[name].function


def _ctx(deps: Deps) -> SimpleNamespace:
    return SimpleNamespace(deps=deps)


def _agent(models):
    return Agent.make("db").instructions("x").database(models).output(str).build()


def test_write_tools_require_approval():
    agent = _agent({"feedback": Feedback})
    for name in ("db_create", "db_update", "db_delete"):
        assert agent._function_toolset.tools[name].requires_approval is True
    for name in ("db_find", "db_get", "db_count", "db_list_models"):
        assert agent._function_toolset.tools[name].requires_approval is False


async def test_database_crud(repos, deps: Deps):
    agent = _agent({"feedback": Feedback, "feedback_r": FeedbackRepo})
    ctx = _ctx(deps)

    assert "feedback" in await _fn(agent, "db_list_models")(ctx)
    assert "rating" in await _fn(agent, "db_describe")(ctx, "feedback")

    created = await _fn(agent, "db_create")(ctx, "feedback", {"rating": 5, "comment": "great"})
    assert "created feedback" in created

    found = await _fn(agent, "db_find")(ctx, "feedback", {"rating": 5})
    assert "great" in found
    assert await _fn(agent, "db_count")(ctx, "feedback") == "1"
    # Repository subclasses are accepted too.
    assert await _fn(agent, "db_count")(ctx, "feedback_r") == "1"

    record = (await repos.feedback.list())[0]
    assert await _fn(agent, "db_get")(ctx, "feedback", record.id) != "(not found)"

    assert "updated" in await _fn(agent, "db_update")(ctx, "feedback", record.id, {"rating": 1})
    assert (await repos.feedback.list())[0].rating == 1
    assert "deleted" in await _fn(agent, "db_delete")(ctx, "feedback", record.id)
    assert await repos.feedback.list() == []


async def test_database_rejects_unknown_fields_and_owner_id(repos, deps: Deps):
    agent = _agent({"feedback": Feedback})
    ctx = _ctx(deps)
    assert (await _fn(agent, "db_create")(ctx, "feedback", {"nope": 1})).startswith("ERROR")
    assert (await _fn(agent, "db_create")(ctx, "feedback", {"owner_id": "x"})).startswith("ERROR")
    assert (await _fn(agent, "db_find")(ctx, "ghost", {})).startswith("ERROR")


async def test_database_is_owner_scoped(repos, deps: Deps):
    await repos.feedback.add(rating=3, conversation_id="mine")
    repos.session.add(Feedback(owner_id="other", rating=9, comment="secret"))
    await repos.session.flush()
    agent = _agent({"feedback": Feedback})
    found = await _fn(agent, "db_find")(_ctx(deps), "feedback", {})
    assert "secret" not in found
    assert "mine" in found
    assert await _fn(agent, "db_count")(_ctx(deps), "feedback") == "1"


async def test_database_writes_audit(repos, deps: Deps):
    agent = _agent({"feedback": Feedback})
    await _fn(agent, "db_create")(_ctx(deps), "feedback", {"rating": 2})
    actions = [entry.action for entry in await repos.audit.entries()]
    assert "db.create" in actions
    assert await repos.audit.verify() is True
