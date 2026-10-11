import pytest

from agentkit.errors import (
    AgentKitError,
    DependencyMissing,
    NotFound,
    PermissionDenied,
)
from agentkit.policy import ALLOW, APPROVE, DENY, ToolPolicy


def test_policy_decisions():
    policy = ToolPolicy(allow={"read", "write"}, deny={"drop"}, require_approval={"write"})
    assert policy.decision("read") == ALLOW
    assert policy.decision("write") == APPROVE
    assert policy.decision("drop") == DENY
    assert policy.decision("other") == DENY  # not in allow-list
    assert policy.approvals_required("write") is True


def test_policy_check_raises():
    policy = ToolPolicy(deny={"rm"})
    with pytest.raises(PermissionDenied):
        policy.check("rm")
    policy.check("safe")


def test_error_codes_and_payload():
    assert NotFound("nope").code == "not_found"
    assert DependencyMissing("x").code == "dependency_missing"
    payload = AgentKitError("boom", detail={"k": 1}).to_dict()
    assert payload["error"]["code"] == "error"
    assert payload["error"]["detail"] == {"k": 1}
    assert NotFound("nope").http_status == 404
