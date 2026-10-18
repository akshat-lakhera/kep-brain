"""Error envelope `{error: {code, message, request_id, details}}` (02 §11.4).

Messages come from a fixed allow-list keyed by code, so internal exception
text never reaches a client (TRD-SR-025).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)

MESSAGES: dict[str, tuple[int, str]] = {
    "bad_request": (400, "The request is not valid."),
    "validation_error": (422, "The request parameters are not valid."),
    "unauthorized": (401, "A valid bearer token is required."),
    "forbidden": (403, "This operation is not allowed."),
    "not_found": (404, "The requested resource does not exist."),
    "method_not_allowed": (405, "The method is not allowed on this path."),
    "kep_not_found": (404, "No KEP matches that reference."),
    "tool_not_found": (404, "No tool with that name is registered."),
    "ambiguous_reference": (409, "The reference matches more than one KEP."),
    "payload_too_large": (413, "The request body is too large."),
    "rate_limited": (429, "Too many requests; retry later."),
    "graph_unavailable": (503, "The graph database is not reachable."),
    "graph_timeout": (504, "The graph query took too long."),
    "provider_error": (502, "The language model provider returned an error."),
    "provider_rate_limited": (503, "The language model provider is rate limiting requests."),
    "budget_exhausted": (503, "Today's question budget is used up; tools still work."),
    "llm_not_configured": (503, "No language model is configured on this server."),
    "internal_error": (500, "An internal error occurred."),
}


class AppError(Exception):
    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        if code not in MESSAGES:
            code = "internal_error"
        super().__init__(code)
        self.code = code
        self.status, self.message = MESSAGES[code]
        self.details = details or {}


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, str) else None


def envelope(code: str, request_id: str | None, details: dict[str, Any] | None = None) -> JSONResponse:
    status, message = MESSAGES.get(code, MESSAGES["internal_error"])
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or {},
            }
        },
        headers=headers,
    )


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}


def _code_for_status(status: int) -> str:
    """Known statuses keep their code; any other client error is a bad request, anything else is internal."""
    if status in _STATUS_CODES:
        return _STATUS_CODES[status]
    return "bad_request" if 400 <= status < 500 else "internal_error"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        response = envelope(exc.code, _request_id(request), exc.details)
        retry = exc.details.get("retry_after_s")
        if exc.status in (429, 503) and isinstance(retry, int) and retry > 0:
            response.headers["Retry-After"] = str(retry)  # RFC 9110 delay-seconds; clients need not parse details
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
        return envelope("validation_error", _request_id(request), {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return envelope(_code_for_status(exc.status_code), _request_id(request))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return envelope("internal_error", _request_id(request))
