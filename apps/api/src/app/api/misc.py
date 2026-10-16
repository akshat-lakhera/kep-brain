"""Meta, graph neighbourhood, tools and eval endpoints."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from app.agent.provider import llm_configured
from app.api.changes import release_keys
from app.api.deps import pool_of, settings_of, variant_for
from app.db.falkordb import GRAPH_KEP, FalkorPool
from app.errors import AppError
from app.eval.questions import judge_questions, latest_summary, load_questions, public_question
from app.ingest.common import iso
from app.memory.store import valid_memory_id
from app.schema.labels import NODE_LABELS, VALID_TO_OPEN
from app.settings import Settings
from app.tools.base import Projector, ToolContext
from app.tools.registry import get_tool, llm_tools

router = APIRouter()

# One cheap count per query: FalkorDB answers label and edge counts from its matrices.
META_COUNTS = {
    "nodes": "MATCH (n) RETURN count(n)",
    "edges": "MATCH ()-[r]->() RETURN count(r)",
    "keps": "MATCH (n:KEP) RETURN count(n)",
    "findings": "MATCH (n:Finding) RETURN count(n)",
    "people": "MATCH (n:Person) RETURN count(n)",
}


async def source_pins(pool: FalkorPool, settings: Settings, graph: str = GRAPH_KEP) -> dict[str, str | None]:
    """Pinned source commits and the ticket snapshot time: from the graph when it records them, else settings."""
    community_sha, tickets_as_of = settings.community_pin_sha, settings.tickets_as_of
    sigs_doc = await pool.ro_query(graph, "MATCH (d:Document {kind: 'sigs_yaml'}) RETURN d.source_sha LIMIT 1")
    if sigs_doc.rows and sigs_doc.rows[0][0]:
        community_sha = str(sigs_doc.rows[0][0])
    enhancements_sha = settings.enhancements_pin_sha
    kep_row = await pool.ro_query(graph, "MATCH (k:KEP) RETURN k.source_url LIMIT 1")
    if kep_row.rows and kep_row.rows[0][0]:
        found = re.search(r"/tree/([0-9a-f]{40})/", str(kep_row.rows[0][0]))
        if found:
            enhancements_sha = found.group(1)
    if tickets_as_of is None:
        seen = await pool.ro_query(graph, "MATCH (i:Issue) RETURN max(i.observed_at)")
        if seen.rows and seen.rows[0][0] is not None:
            tickets_as_of = iso(int(seen.rows[0][0]))
    return {
        "enhancements_sha": enhancements_sha,
        "community_sha": community_sha,
        "tickets_as_of": tickets_as_of,
    }


@router.get("/meta", tags=["meta"])
async def meta(request: Request) -> dict[str, Any]:
    pool, settings = pool_of(request), settings_of(request)
    counts = {"nodes": 0, "edges": 0, "keps": 0, "findings": 0, "people": 0}
    sources: dict[str, str | None] = {
        "enhancements_sha": settings.enhancements_pin_sha,
        "community_sha": settings.community_pin_sha,
        "tickets_as_of": settings.tickets_as_of,
    }
    releases: list[str] = []
    if GRAPH_KEP in await pool.ping():
        for name, query in META_COUNTS.items():
            out = await pool.ro_query(GRAPH_KEP, query)
            counts[name] = int(out.rows[0][0]) if out.rows else 0
        sources = await source_pins(pool, settings)
        releases = await release_keys(pool, GRAPH_KEP)
    return {
        "graph": counts,
        "sources": sources,
        "sigs": settings.sig_list,
        "releases": releases,
        "llm": {"provider": settings.llm_provider, "model": settings.llm_model, "configured": llm_configured(settings)},
        "falkordb_image": settings.falkordb_image,
    }


# Key format → label (03 §3.1), so a neighbourhood lookup hits one key index.
_KEY_LABELS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"^keps/"), ("KEP",)),
    (re.compile(r"^fnd:"), ("Finding",)),
    (re.compile(r"^dec:"), ("Decision",)),
    (re.compile(r"^(sc|ghe):"), ("StatusChange",)),
    (re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{7,40}$"), ("Commit",)),
    (re.compile(r"^[\w.-]+/[\w.-]+#\d+$"), ("Issue", "PullRequest")),
    (re.compile(r"^[\w.-]+/[\w.-]+/pulls/reviews/"), ("Review",)),
    (re.compile(r"^[\w.-]+/[\w.-]+/(issues|pulls)/comments/"), ("Comment",)),
    (re.compile(r"^(sig|wg|committee)-"), ("SIG", "WorkingGroup", "Committee")),
    (re.compile(r"^v\d+\.\d+$"), ("Release",)),
    (re.compile(r"#"), ("Section",)),
    (re.compile(r":"), ("Document", "Alias")),
]
_FALLBACK_LABELS = ("Person", "FeatureGate", "Label", "Release", "Component")


def _labels_for(key: str) -> tuple[str, ...]:
    for pattern, labels in _KEY_LABELS:
        if pattern.search(key):
            return labels
    return _FALLBACK_LABELS


def _hood(label: str, depth: int, limit: int) -> str:
    assert label in NODE_LABELS
    if depth == 1:
        return f"""
MATCH (n:{label} {{key: $key}})-[r]-(m)
WHERE coalesce(r.valid_to, $open) = $open
RETURN n, r, m
ORDER BY type(r), m.key
LIMIT {limit}
"""
    return f"""
MATCH p = (n:{label} {{key: $key}})-[*1..2]-(m)
WHERE all(r IN relationships(p) WHERE coalesce(r.valid_to, $open) = $open)
RETURN p
ORDER BY length(p), m.key
LIMIT {limit}
"""


@router.get("/graph/neighborhood", tags=["graph"])
async def neighborhood(
    request: Request,
    key: str = Query(min_length=1, max_length=400),
    depth: int = Query(default=1, ge=1, le=2),
    limit: int = Query(default=60, ge=1, le=200),
) -> dict[str, Any]:
    pool = pool_of(request)
    variant = variant_for(limit, (20, 60, 120, 200))
    for label in _labels_for(key):
        out = await pool.ro_query(GRAPH_KEP, _hood(label, depth, variant), {"key": key, "open": VALID_TO_OPEN})
        if out.rows:
            return graph_out(out.rows)
    for label in _labels_for(key):
        out = await pool.ro_query(GRAPH_KEP, f"MATCH (n:{label} {{key: $key}}) RETURN n LIMIT 1", {"key": key})
        if out.rows:
            return graph_out(out.rows)
    raise AppError("not_found", {"key": key[:200]})


def graph_out(rows: list[list[Any]]) -> dict[str, Any]:
    """Nodes and edges from raw result rows; ids are evidence ids, never internal ids."""
    from falkordb import Edge, Node, Path

    proj = Projector()
    ids: dict[int, str] = {}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, str]] = {}

    def add_node(n: Node) -> None:
        d = proj.node(n)
        if not d.get("key"):
            return
        eid = d["evidence_id"]
        if n.id is not None:
            ids[n.id] = eid
        nodes.setdefault(eid, {"id": eid, "label": d["label"], "key": d["key"], "title": d["title"], "url": d["url"]})

    pending: list[Edge] = []
    for row in rows:
        for v in row:
            if isinstance(v, Node):
                add_node(v)
            elif isinstance(v, Edge):
                pending.append(v)
            elif isinstance(v, Path):
                for n in v.nodes():
                    add_node(n)
                pending.extend(v.edges())
    for e in pending:
        s, t = ids.get(e.src_node), ids.get(e.dest_node)
        if s and t:
            edges.setdefault((s, t, e.relation), {"source": s, "target": t, "type": e.relation})
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


@router.get("/tools", tags=["tools"])
async def list_tools() -> dict[str, Any]:
    return {
        "items": [
            {"name": t.name, "description": t.description, "params_schema": t.params_schema()} for t in llm_tools()
        ]
    }


@router.post("/tools/{name}", tags=["tools"])
async def call_tool(
    request: Request, name: str, body: Annotated[dict[str, Any] | None, Body()] = None
) -> dict[str, Any]:
    tool = get_tool(name)
    memory_id = valid_memory_id(request.headers.get("x-kep-memory-id"))
    from pydantic import ValidationError

    try:
        result = await tool.invoke(ToolContext(pool=pool_of(request), memory_id=memory_id), body or {})
    except ValidationError as exc:
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
        raise AppError("validation_error", {"fields": fields, "errors": [e["msg"] for e in exc.errors()][:5]}) from exc
    return result.model_dump()


@router.get("/eval/questions", tags=["eval"])
async def eval_questions() -> dict[str, Any]:
    return {"questions": [public_question(q) for q in judge_questions(load_questions())]}


@router.get("/eval/latest", tags=["eval"])
async def eval_latest() -> JSONResponse:
    return JSONResponse(latest_summary())
