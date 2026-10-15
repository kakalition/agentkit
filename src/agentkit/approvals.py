"""Human-in-the-loop approval wiring for PydanticAI deferred tools.

Mark a tool ``@agent.tool(requires_approval=True)`` and add
:data:`approval_capability` to the agent; when the tool is called, the handler
asks ``deps.approve`` and resolves the batch inline so the run continues.
"""

from __future__ import annotations

from typing import Any

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
    from agentkit.foundation.facade import emit

    await emit(
        "approval.asked",
        requests=[
            {"tool_call_id": request.tool_call_id, "tool_name": request.tool_name}
            for request in pending
        ],
    )
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


class ApprovalQueue:
    """An in-process queue bridging deferred approvals to a UI.

    ``request`` (an ``ApprovalCallback``) suspends the run until ``decide`` is
    called for each pending tool call — e.g. from a web UI. Pending requests are
    inspectable via :meth:`pending`.
    """

    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, Any] = {}

    async def request(self, requests: list[ApprovalRequest]) -> dict[str, bool]:
        import asyncio

        loop = asyncio.get_running_loop()
        futures: dict[str, Any] = {}
        for request in requests:
            self._pending[request.tool_call_id] = request
            futures[request.tool_call_id] = loop.create_future()
            self._futures[request.tool_call_id] = futures[request.tool_call_id]
        try:
            results: dict[str, bool] = {}
            for tool_call_id, future in futures.items():
                results[tool_call_id] = bool(await future)
            return results
        finally:
            for tool_call_id in futures:
                self._pending.pop(tool_call_id, None)
                self._futures.pop(tool_call_id, None)

    def pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    def decide(self, tool_call_id: str, approved: bool) -> bool:
        future = self._futures.get(tool_call_id)
        if future is None or future.done():
            return False
        future.set_result(bool(approved))
        return True

    def approve_all(self, approved: bool = True) -> int:
        decided = 0
        for tool_call_id in list(self._futures):
            if self.decide(tool_call_id, approved):
                decided += 1
        return decided


__all__ = ["ApprovalQueue", "approval_capability", "approval_handler", "auto_approver"]
