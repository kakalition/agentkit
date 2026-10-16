"""Linear gateway: post comments on issues via the Linear GraphQL API.

The conversation id is ``linear:<issueId>``; outbound text becomes a comment.
"""

from __future__ import annotations

from typing import Any

from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["LinearGateway"]

_COMMENT_MUTATION = (
    "mutation CommentCreate($input: CommentCreateInput!) { commentCreate(input: $input) { success } }"
)


class LinearGateway(Gateway):
    name = "linear"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        allowed_channel_ids: Any = None,
        api_key: str | None = None,
        base_url: str = "https://api.linear.app/graphql",
    ) -> None:
        super().__init__(app, settings=settings, allowed_channel_ids=allowed_channel_ids)
        self.api_key = api_key or getattr(self.settings, "linear_api_key", None)
        self.base_url = base_url

    @staticmethod
    def _issue(conversation_id: str) -> str:
        return conversation_id.split(":", 1)[1] if ":" in conversation_id else conversation_id

    async def send(self, conversation_id: str, text: str) -> None:
        api_key = self.api_key or (
            getattr(self.settings, "linear_api_key", None) if self.settings else None
        )
        if not api_key:
            raise GatewayError("the linear gateway needs LINEAR_API_KEY to be set")
        import httpx

        payload = {
            "query": _COMMENT_MUTATION,
            "variables": {"input": {"issueId": self._issue(conversation_id), "body": text}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.base_url, json=payload, headers={"Authorization": api_key}
            )
        if response.status_code >= 400:
            raise GatewayError(f"linear API error {response.status_code}")

    async def start(self) -> None:
        return None
