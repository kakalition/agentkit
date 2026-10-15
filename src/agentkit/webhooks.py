"""Outbound webhooks: HMAC-signed JSON deliveries with bounded retries.

A :class:`WebhookDispatcher` subscribes to lifecycle events, matches them against
each owner's subscriptions, POSTs the payload with an HMAC-SHA256 signature, and
records every attempt in the ``webhook_deliveries`` log.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

from agentkit.logging import get_logger

log = get_logger("agentkit.webhooks")

DEFAULT_EVENTS = (
    "turn.end",
    "learning.reflected",
    "db.create",
    "db.update",
    "db.delete",
    "schedule.upsert",
)


def sign(secret: str, body: bytes) -> str:
    """The ``sha256=<hex>`` HMAC signature header value for a payload."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _matches(subscribed: list[str], event: str) -> bool:
    return "*" in subscribed or event in subscribed


class WebhookDispatcher:
    """Deliver lifecycle events to registered webhooks."""

    def __init__(
        self,
        runtime: Any,
        *,
        client: Any = None,
        max_attempts: int = 3,
        timeout: float = 10.0,
        backoff_base: float = 0.25,
    ) -> None:
        self.runtime = runtime
        self._client = client
        self.max_attempts = max(1, int(max_attempts))
        self.timeout = timeout
        self.backoff_base = backoff_base

    def subscribe(self, dispatcher: Any, events: tuple[str, ...] = DEFAULT_EVENTS) -> None:
        for name in events:
            dispatcher.listen(name, self._listener(name))

    def _listener(self, event: str) -> Any:
        async def handle(ev: Any) -> Any:
            return await self.emit(getattr(ev, "name", event), dict(getattr(ev, "payload", {})))

        return handle

    async def emit(self, event: str, payload: dict[str, Any], *, owner_id: str | None = None) -> list[dict[str, Any]]:
        """Deliver ``event`` to every matching enabled webhook; returns results."""
        from agentkit.runtime import repositories

        results: list[dict[str, Any]] = []
        async with repositories(self.runtime, owner_id) as repos:
            hooks = await repos.webhooks.list(enabled_only=True)
            for hook in hooks:
                if not _matches(_events(hook.events), event):
                    continue
                results.append(await self._deliver_one(repos, hook, event, payload))
        return results

    async def _deliver_one(self, repos: Any, hook: Any, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"event": event, "data": payload}, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-AgentKit-Event": event,
        }
        if hook.secret:
            headers["X-AgentKit-Signature"] = sign(hook.secret, body)

        status, error = "failed", ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                await self._post(hook.url, body, headers)
                status, error, attempts = "ok", "", attempt
                break
            except Exception as exc:  # network / HTTP error → retry
                error = f"{type(exc).__name__}: {exc}"
                attempts = attempt
                if attempt < self.max_attempts and self.backoff_base:
                    await asyncio.sleep(self.backoff_base * (2 ** (attempt - 1)))
        await repos.webhook_deliveries.record(
            webhook_id=hook.id,
            event=event,
            payload=body.decode("utf-8"),
            status=status,
            attempts=attempts,
            error=error,
        )
        if status != "ok":
            log.warning("webhook %s delivery of %s failed: %s", hook.id, event, error)
        return {"webhook_id": hook.id, "event": event, "status": status, "attempts": attempts}

    async def _post(self, url: str, body: bytes, headers: dict[str, str]) -> None:
        if self._client is not None:
            response = await self._client.post(url, content=body, headers=headers, timeout=self.timeout)
        else:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, content=body, headers=headers)
        response.raise_for_status()


def _events(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ["*"]
    return [str(item) for item in value] if isinstance(value, list) else ["*"]


__all__ = ["DEFAULT_EVENTS", "WebhookDispatcher", "sign"]
