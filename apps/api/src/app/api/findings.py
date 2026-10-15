"""Audit endpoints: the Finding list with its summary block, and one finding with evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.audit_check import hand_check_summary, load_verdicts, with_verdicts
from app.api.deps import pool_of, rows_of
from app.api.keps import FINDING_FIELDS
from app.db.falkordb import GRAPH_KEP
from app.errors import AppError
from app.tools.base import Projector
from app.tools.cypher import unique_comprehension_vars

router = APIRouter(tags=["findings"])

LIST = f"""
MATCH (f:Finding)
WHERE ($kind = '' OR f.kind = $kind) AND ($state = '' OR f.state = $state)
MATCH (k:KEP {{key: f.kep_path}})
WHERE $sig = '' OR k.owning_sig = $sig
RETURN {FINDING_FIELDS}
ORDER BY f.kind, f.kep_path, f.key
LIMIT 1000
"""

ONE = unique_comprehension_vars(f"""
MATCH (f:Finding {{key: $key}})
MATCH (k:KEP {{key: f.kep_path}})
RETURN {FINDING_FIELDS}, k AS kep,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE coalesce(r.valid_to, $open) = $open | i] AS issues,
 [(f)-[:EVIDENCED_BY]->(e) | e] AS evidence_nodes
LIMIT 1
""")


@router.get("/findings")
async def list_findings(
    request: Request,
    kind: str = Query(default="", max_length=60),
    sig: str = Query(default="", max_length=60),
    state: str = Query(default="", max_length=30),
) -> dict[str, Any]:
    out = await pool_of(request).ro_query(GRAPH_KEP, LIST, {"kind": kind, "sig": sig, "state": state})
    items = with_verdicts(rows_of(out), load_verdicts())
    return {
        "summary": {
            "flagged_keps": len({i["kep_path"] for i in items}),
            "total": len(items),
            "by_kind": dict(Counter(i["kind"] for i in items)),
            "by_sig": dict(Counter(i["owning_sig"] for i in items)),
            **hand_check_summary(items),
        },
        "items": items,
    }


@router.get("/findings/{key:path}")
async def get_finding(request: Request, key: str) -> dict[str, Any]:
    from app.schema.labels import VALID_TO_OPEN

    out = await pool_of(request).ro_query(GRAPH_KEP, ONE, {"key": key, "open": VALID_TO_OPEN})
    if not out.rows:
        raise AppError("not_found", {"key": key[:200]})
    row = dict(zip(out.header, out.rows[0], strict=False))
    proj = Projector()
    proj.value([row.pop("kep"), row.pop("issues") or [], row.pop("evidence_nodes") or []])
    row["evidence"] = [e.model_dump() for e in proj.evidence.values()]
    return with_verdicts([row], load_verdicts())[0]
