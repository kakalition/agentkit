"""A minimal OpenAI-compatible API mapped to the app's ``answer`` callable.

``GET /v1/models`` and ``POST /v1/chat/completions`` (streaming SSE + JSON), so
existing OpenAI clients can talk to an agentkit agent. Opt-in via
``OPENAI_API_ENABLED``; authentication uses the same ``Authenticator`` as the web
UI, and each completion records usage.
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentkit.runtime import repositories
from agentkit.security import Actor
from agentkit.webui.auth import require_actor
from agentkit.webui.context import WebUIContext, get_context

router = APIRouter(tags=["openai"])


class ChatMessage(BaseModel):
    role: str
    content: Any = ""


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    conversation_id: str | None = None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
        return " ".join(chunks)
    return ""


def _last_user(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return _content_text(message.content)
    return _content_text(messages[-1].content) if messages else ""


def _check_enabled(settings: Any) -> None:
    if not getattr(settings, "openai_api_enabled", False):
        raise HTTPException(status_code=404, detail="the OpenAI-compatible API is disabled")


def _usage_dict(result: Any) -> dict[str, int]:
    raw = getattr(result, "usage", None) or {}
    try:
        prompt = int(raw.get("input_tokens", 0) or 0)
        completion = int(raw.get("output_tokens", 0) or 0)
        total = int(raw.get("total_tokens", 0) or 0) or (prompt + completion)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        prompt = completion = total = 0
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


@router.get("/v1/models")
async def list_models(
    ctx: WebUIContext = Depends(get_context), actor: Actor = Depends(require_actor)
) -> dict[str, Any]:
    _check_enabled(ctx.settings)
    return {
        "object": "list",
        "data": [
            {
                "id": ctx.settings.model_name,
                "object": "model",
                "created": 0,
                "owned_by": "agentkit",
            }
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    ctx: WebUIContext = Depends(get_context),
    actor: Actor = Depends(require_actor),
) -> Any:
    _check_enabled(ctx.settings)
    if ctx.answer is None:
        raise HTTPException(status_code=503, detail="chat is not enabled for this agent")
    conversation_id = body.conversation_id or f"openai:{actor.owner_id}"
    prompt = _last_user(body.messages)
    model_name = body.model or ctx.settings.model_name
    result = await ctx.answer(conversation_id, prompt, actor=actor)
    usage = _usage_dict(result)
    async with repositories(ctx.runtime, actor.owner_id) as repos:
        await repos.usage.add(
            conversation_id=conversation_id,
            kind="api",
            model=model_name,
            requests=1,
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
        )

    completion_id = f"chatcmpl-{uuid4().hex}"
    created = int(time.time())
    if not body.stream:
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.output},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }

    def _sse(payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    def _chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }

    async def _stream() -> Any:
        yield _sse(_chunk({"role": "assistant", "content": ""}))
        output = result.output or ""
        step = max(1, len(output) // 24 or 1)
        for start in range(0, len(output), step):
            yield _sse(_chunk({"content": output[start : start + step]}))
        yield _sse(_chunk({}, finish="stop"))
        yield "data: [DONE]\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
