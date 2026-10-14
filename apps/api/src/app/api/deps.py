"""Shared request helpers for the HTTP routes."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from fastapi import Request

from app.db.falkordb import FalkorPool, QueryOutput
from app.errors import AppError
from app.settings import Settings


def pool_of(request: Request) -> FalkorPool:
    pool: FalkorPool = request.app.state.db
    return pool


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def rows_of(out: QueryOutput) -> list[dict[str, Any]]:
    return [dict(zip(out.header, row, strict=False)) for row in out.rows]


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, str) else ""


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limit per client address (single api replica)."""

    def __init__(self, window_s: float = 600.0) -> None:
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(self.window_s - (now - hits[0])) + 1
                raise AppError("rate_limited", {"retry_after_s": retry})
            hits.append(now)


ASK_LIMITER = RateLimiter()
