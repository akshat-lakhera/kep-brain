from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api import deps
from app.api.deps import AskLimiter, client_ip
from app.errors import AppError, install_error_handlers
from app.middleware import BodyLimitMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.settings import Settings


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(BodyLimitMiddleware, max_bytes=100)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/v1/ask")
    async def ask(request: Request) -> dict[str, int]:
        return {"n": len(await request.body())}

    @app.get("/v1/keps")
    async def keps() -> dict[str, str]:
        return {"ok": "1"}

    return app


def test_headers_and_no_store() -> None:
    c = TestClient(_app())
    r = c.post("/v1/ask", content=b"x")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert "cache-control" not in c.get("/v1/keps").headers


def test_body_limit_header_and_streamed() -> None:
    c = TestClient(_app())
    assert c.post("/v1/ask", content=b"x" * 100).status_code == 200
    r = c.post("/v1/ask", content=b"x" * 101)
    assert r.status_code == 413
    err = r.json()["error"]
    assert err["code"] == "payload_too_large" and err["request_id"]
    r2 = c.post("/v1/ask", content=(b"x" * 60 for _ in range(3)))
    assert r2.status_code == 413
    assert set(r2.json()["error"]) == {"code", "message", "request_id", "details"}


def _req(host: str, xff: str | None, trust: bool) -> Any:
    headers = {"x-forwarded-for": xff} if xff else {}
    state = SimpleNamespace(settings=Settings(trust_proxy=trust))
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers, app=SimpleNamespace(state=state))


def test_proxy_handling() -> None:
    assert client_ip(_req("10.0.0.1", "1.2.3.4, 5.6.7.8", False)) == "10.0.0.1"
    assert client_ip(_req("10.0.0.1", "1.2.3.4, 5.6.7.8", True)) == "5.6.7.8"
    assert client_ip(_req("10.0.0.1", None, True)) == "10.0.0.1"


def test_daily_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(ask_daily_cap=2))
    lim = AskLimiter()
    lim.check("a", 10)
    lim.check("b", 10)
    with pytest.raises(AppError) as ei:
        lim.check("c", 10)
    assert ei.value.code == "rate_limited"
    assert 1 <= ei.value.details["retry_after_s"] <= 86400
    lim._day = "1999-01-01"  # a new UTC day resets the counter
    lim.check("c", 10)


def test_unsupported_method_is_405_not_500() -> None:
    c = TestClient(_app())
    r = c.put("/v1/keps")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_rate_limited_errors_carry_retry_after() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/limited")
    async def limited() -> None:
        raise AppError("rate_limited", {"retry_after_s": 42})

    r = TestClient(app).get("/limited")
    assert r.status_code == 429 and r.headers["retry-after"] == "42"
    assert r.json()["error"]["details"]["retry_after_s"] == 42


def test_rate_limiter_drops_idle_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 100.0])
    monkeypatch.setattr(deps.time, "monotonic", lambda: next(clock))
    limiter = deps.RateLimiter(window_s=10.0)
    limiter.SWEEP_EVERY = 3
    for i in range(3):
        limiter.check(f"10.0.0.{i}", 5)
    assert list(limiter._hits) == ["10.0.0.2"]
