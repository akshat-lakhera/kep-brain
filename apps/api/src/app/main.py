"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db.falkordb import GRAPH_KEP, FalkorPool
from app.errors import AppError, install_error_handlers
from app.logging import configure_logging
from app.middleware import BodyLimitMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db = FalkorPool(settings)
        try:
            yield
        finally:
            app.state.db.close()

    app = FastAPI(
        title="KEP Brain API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-Kep-Memory-Id"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        try:
            graphs = await request.app.state.db.ping()
        except AppError:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        status = "ready" if GRAPH_KEP in graphs else "empty"
        return JSONResponse(status_code=200 if status == "ready" else 503, content={"status": status})

    from app.api.routes import router

    app.include_router(router, prefix="/v1")
    return app
