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
