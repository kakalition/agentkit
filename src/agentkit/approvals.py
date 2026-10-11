"""Human-in-the-loop approval wiring for PydanticAI deferred tools.

Mark a tool ``@agent.tool(requires_approval=True)`` and add
:data:`approval_capability` to the agent; when the tool is called, the handler
asks ``deps.approve`` and resolves the batch inline so the run continues.
"""

from __future__ import annotations

from pydantic_ai.capabilities import HandleDeferredToolCalls
from pydantic_ai.tools import (
    DeferredToolRequests,
    DeferredToolResults,
    RunContext,
    ToolApproved,
    ToolDenied,
)

from agentkit.deps import ApprovalRequest, Deps


async def approval_handler(
    ctx: RunContext[Deps], requests: DeferredToolRequests
) -> DeferredToolResults | None:
    pending = [
        ApprovalRequest(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            args=call.args if isinstance(call.args, dict) else {},
        )
        for call in requests.approvals
    ]
    if not pending:
        return None
    if ctx.deps.approve is None:
        decided: dict[str, bool] = {request.tool_call_id: False for request in pending}
    else:
        decided = await ctx.deps.approve(pending)
    approvals: dict[str, bool | ToolApproved | ToolDenied] = {
        request.tool_call_id: bool(decided.get(request.tool_call_id, False))
        for request in pending
    }
    return DeferredToolResults(approvals=approvals)


approval_capability = HandleDeferredToolCalls(handler=approval_handler)


def auto_approver(requests: list[ApprovalRequest]) -> dict[str, bool]:
    """An ``ApprovalCallback`` that approves everything (use with care)."""
    return {request.tool_call_id: True for request in requests}
