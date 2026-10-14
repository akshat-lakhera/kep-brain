"""The `/v1` router (02 §12, 06 C3)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import ask, findings, keps, misc
from app.memory import routes as memory_routes

router = APIRouter()
router.include_router(misc.router)
router.include_router(keps.router)
router.include_router(findings.router)
router.include_router(ask.router)
router.include_router(memory_routes.router)
