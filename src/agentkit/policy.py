"""Tool RBAC + approval policy.

A :class:`ToolPolicy` decides, per tool name, whether a call is allowed, denied,
or must be approved. Compose it into the agent's approval flow so decisions are
declarative instead of baked into a callback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentkit.errors import PermissionDenied

ALLOW = "allow"
DENY = "deny"
APPROVE = "approve"


@dataclass
class ToolPolicy:
    """Allow/deny/approve rules for tool calls.

    * ``allow`` — if set, only these tools are permitted (allow-list).
    * ``deny`` — always refused (takes precedence over ``allow``).
    * ``require_approval`` — permitted only with human approval.
    """

    allow: set[str] | None = None
    deny: set[str] = field(default_factory=set)
    require_approval: set[str] = field(default_factory=set)
    require_roles: dict[str, set[str]] = field(default_factory=dict)

    def decision(self, tool: str) -> str:
        if tool in self.deny:
            return DENY
        if self.allow is not None and tool not in self.allow:
            return DENY
        if tool in self.require_approval:
            return APPROVE
        return ALLOW

    def is_allowed(self, tool: str) -> bool:
        return self.decision(tool) != DENY

    def roles_for(self, tool: str) -> set[str]:
        return set(self.require_roles.get(tool, ()))

    def check(self, tool: str, actor: Any = None) -> None:
        """Raise :class:`PermissionDenied` if the tool is not allowed for ``actor``."""
        if self.decision(tool) == DENY:
            raise PermissionDenied(f"tool not permitted: {tool}", detail={"tool": tool})
        required = self.roles_for(tool)
        if required and (actor is None or not actor.has_role(*required)):
            raise PermissionDenied(
                f"tool requires role: {tool}",
                detail={"tool": tool, "roles": sorted(required)},
            )

    def approvals_required(self, tool: str) -> bool:
        return self.decision(tool) == APPROVE


# Tools that mutate the world and should be approved by default.
DEFAULT_APPROVAL_TOOLS = (
    "run_command",
    "write_file",
    "delete_file",
    "send_email",
    "send_to",
)

# Native-tool write tools (see :mod:`agentkit.toolkits`): each mutates durable
# state or sends egress, so they are approval-gated by :func:`default_policy`.
NATIVE_APPROVAL_TOOLS = (
    "db_create",
    "db_update",
    "db_delete",
    "schedule_task",
    "run_schedule_now",
    "enqueue_task",
    "notify",
    "replace_document",
    "forget_document",
    "save_skill",
    "update_skill",
)


def native_policy() -> ToolPolicy:
    """Approval policy for the native toolkits (writes only)."""
    return ToolPolicy(require_approval=set(NATIVE_APPROVAL_TOOLS))


NATIVE_TOOLS_POLICY = native_policy()


def default_policy() -> ToolPolicy:
    """The default safety policy: approve destructive/egress tools, allow the rest."""
    return ToolPolicy(require_approval=set(DEFAULT_APPROVAL_TOOLS) | set(NATIVE_APPROVAL_TOOLS))
