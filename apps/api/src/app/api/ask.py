"""`POST /v1/ask` and `POST /v1/ask/stream` (02 §6, §12.1; 06 C3s)."""

from __future__ import annotations

import asyncio
import hmac
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent.cache import AnswerCache
from app.agent.loop import Agent
from app.agent.provider import llm_configured
from app.api.deps import ASK_LIMITER, client_ip, pool_of, request_id_of, settings_of
from app.errors import MESSAGES, AppError
from app.memory import store as memory_store

log = structlog.get_logger(__name__)
router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    memory_id: str | None = Field(default=None, max_length=40)


def _agent(request: Request) -> Agent:
    agent: Agent | None = getattr(request.app.state, "agent", None)
    if agent is None:
        agent = Agent(pool_of(request), settings_of(request))
        request.app.state.agent = agent
    return agent


def _prepare(request: Request, body: AskRequest) -> tuple[Agent, str | None]:
    settings = settings_of(request)
    if not llm_configured(settings):
        raise AppError("llm_not_configured")
    ASK_LIMITER.check(client_ip(request), settings.ask_rate_limit_per_10m)
    memory_id = memory_store.valid_memory_id(body.memory_id or request.headers.get("x-kep-memory-id"))
    return _agent(request), memory_id


@router.post("/ask")
async def ask(request: Request, body: AskRequest) -> dict[str, Any]:
    agent, memory_id = _prepare(request, body)
    return await agent.ask(body.question.strip(), request_id_of(request), memory_id)


@router.delete("/answers/cache")
async def clear_answer_cache(request: Request) -> dict[str, int]:
    token = settings_of(request).admin_token
    header = request.headers.get("authorization", "")
    supplied = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    # Bytes, not str: compare_digest raises TypeError on a non-ASCII str, which would surface as a 500.
    expected = token.get_secret_value().encode() if token is not None else b""
    if not expected or not supplied or not hmac.compare_digest(supplied.encode("utf-8", "replace"), expected):
        raise AppError("unauthorized")
    return {"deleted": await AnswerCache(pool_of(request)).clear()}


@router.post("/ask/stream")
async def ask_stream(request: Request, body: AskRequest) -> EventSourceResponse:
    agent, memory_id = _prepare(request, body)
    request_id = request_id_of(request)
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def runner() -> None:
        try:
            await agent.ask(body.question.strip(), request_id, memory_id, emit)
        except AppError as exc:
            await queue.put(("error", {"code": exc.code, "message": MESSAGES[exc.code][1], "request_id": request_id}))
        except Exception:  # noqa: BLE001 - reported to the client as an error event
            log.exception("ask_stream_failed")
            await queue.put(("error", {"code": "internal_error", "message": MESSAGES["internal_error"][1],
                                       "request_id": request_id}))  # fmt: skip
        finally:
            await queue.put(None)

    async def events() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                yield {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(events(), headers={"X-Request-ID": request_id})
