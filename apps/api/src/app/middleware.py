"""Pure-ASGI request-id middleware (TRD-SR-004).

An inbound `X-Request-ID` is kept only if it matches a strict pattern;
otherwise a new id is generated. The id is bound into structlog context
and echoed on the response.
"""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import envelope

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
log = structlog.get_logger("http")


def accept_request_id(value: str | None) -> str:
    if value and REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                inbound = value.decode("latin-1")
                break
        request_id = accept_request_id(inbound)
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                path = scope.get("path", "")
                if path not in ("/health", "/ready"):
                    log.info(
                        "request",
                        method=scope.get("method"),
                        path=path,
                        status=status_holder.get("status"),
                        ms=round((time.perf_counter() - started) * 1000, 1),
                    )


NO_STORE_PREFIXES = ("/v1/ask", "/v1/memory", "/v1/agents")


class SecurityHeadersMiddleware:
    """Adds baseline security headers; `Cache-Control: no-store` on ask and memory routes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        no_store = str(scope.get("path", "")).startswith(NO_STORE_PREFIXES)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if no_store:
                    headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                present = {k.lower() for k, _ in headers}
                for name, value in ((b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")):
                    if name not in present:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Rejects request bodies over `max_bytes` with a 413 error envelope (by header, and while streaming)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = scope.get("state", {}).get("request_id")
        declared = next((v for k, v in scope.get("headers", []) if k == b"content-length"), None)
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await envelope("payload_too_large", rid)(scope, receive, send)
            return

        seen = 0
        started = False

        async def receive_wrapper() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except _BodyTooLarge:
            if started:
                raise
            await envelope("payload_too_large", rid)(scope, receive, send)
