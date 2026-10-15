"""`GET /v1/risk`: knowledge risk on active KEPs (single approvers, approver load, idle people).

The report and its thresholds are defined in `app.tools.t03.risk` (shared with the `knowledge_risk` tool).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import graph_of, pool_of, rows_of
from app.errors import AppError
from app.schema.labels import VALID_TO_OPEN
from app.tools.t03.risk import knowledge_risk

router = APIRouter(tags=["risk"])

SIG_EXISTS = "MATCH (k:KEP {owning_sig: $sig}) RETURN count(k) AS n"


@router.get("/risk")
async def get_risk(
    request: Request, sig: str = Query(default="", max_length=60, pattern=r"^[a-z0-9-]*$")
) -> dict[str, Any]:
    pool, graph = pool_of(request), graph_of(request)
    if sig:
        rows = rows_of(await pool.ro_query(graph, SIG_EXISTS, {"sig": sig}))
        if not rows or not rows[0]["n"]:
            raise AppError("not_found", {"sig": sig})

    async def query(template: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        out = await pool.ro_query(graph, template, {"open": VALID_TO_OPEN, **args}, timeout_ms=5000)
        return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows_of(out)]

    return await knowledge_risk(query, sig or None)
