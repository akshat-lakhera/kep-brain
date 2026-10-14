"""Memory and agent-board routes (T02). Mounted under `/v1` by the app factory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from app.api.deps import pool_of
from app.errors import AppError
from app.memory import store
from app.worker import coordinate

router = APIRouter(tags=["memory"])


def _memory_id(header: str | None) -> str:
    memory_id = store.valid_memory_id(header)
    if memory_id is None:
        raise AppError("bad_request", {"reason": "X-Kep-Memory-Id must be a 26 character ULID"})
    return memory_id


@router.get("/memory/me")
async def memory_me(
    request: Request, x_kep_memory_id: str | None = Header(default=None, alias="X-Kep-Memory-Id")
) -> dict[str, Any]:
    return await store.get_memory(pool_of(request), _memory_id(x_kep_memory_id))


@router.delete("/memory/me")
async def memory_forget(
    request: Request, x_kep_memory_id: str | None = Header(default=None, alias="X-Kep-Memory-Id")
) -> dict[str, Any]:
    return {"deleted": await store.forget(pool_of(request), _memory_id(x_kep_memory_id))}


@router.delete("/memory/me/facts/{key}")
async def memory_forget_fact(
    key: str, request: Request, x_kep_memory_id: str | None = Header(default=None, alias="X-Kep-Memory-Id")
) -> dict[str, Any]:
    if not await store.forget_fact(pool_of(request), _memory_id(x_kep_memory_id), key):
        raise AppError("not_found", {"reason": "no such fact in this memory"})
    return {"deleted": True}


@router.get("/agents/board")
async def agents_board(request: Request) -> dict[str, Any]:
    return await coordinate.board(pool_of(request))
