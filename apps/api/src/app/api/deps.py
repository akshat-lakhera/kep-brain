"""Shared request helpers for the HTTP routes."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from fastapi import Request

from app.db.falkordb import GRAPH_KEP, GRAPH_OPS, FalkorPool, QueryOutput
from app.errors import AppError
from app.settings import Settings, get_settings


def pool_of(request: Request) -> FalkorPool:
    pool: FalkorPool = request.app.state.db
    return pool


def graph_of(request: Request) -> str:
    """The knowledge graph the read routes query (`kep`; tests point it at a fixture graph)."""
    return str(getattr(request.app.state, "kep_graph", GRAPH_KEP))


def ops_graph_of(request: Request) -> str:
    return str(getattr(request.app.state, "ops_graph", GRAPH_OPS))


def settings_of(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def rows_of(out: QueryOutput) -> list[dict[str, Any]]:
    return [dict(zip(out.header, row, strict=False)) for row in out.rows]


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, str) else ""


def client_ip(request: Request) -> str:
    """Peer address; X-Forwarded-For (last hop appended by our proxy) only when TRUST_PROXY is set."""
    settings: Settings | None = getattr(request.app.state, "settings", None)
    if (settings or get_settings()).trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1][:64]
    return request.client.host if request.client else "unknown"


def _seconds_to_utc_midnight(now: datetime) -> int:
    return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)


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


class AskLimiter(RateLimiter):
    """Per-address window plus a global per-UTC-day cap on LLM asks (in-process)."""

    def __init__(self, window_s: float = 600.0) -> None:
        super().__init__(window_s)
        self._day = ""
        self._count = 0
        self._day_lock = Lock()

    def check(self, key: str, limit: int) -> None:
        cap = get_settings().ask_daily_cap
        now = datetime.now(UTC)
        day = now.strftime("%Y-%m-%d")
        with self._day_lock:
            if day != self._day:
                self._day, self._count = day, 0
            if self._count >= cap:
                raise AppError("rate_limited", {"retry_after_s": _seconds_to_utc_midnight(now), "scope": "daily"})
        super().check(key, limit)
        with self._day_lock:
            self._count += 1


ASK_LIMITER = AskLimiter()
