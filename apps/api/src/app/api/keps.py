"""KEP endpoints: list/search, detail, history, decisions (02 §12)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.audit_check import load_verdicts, with_verdicts
from app.api.deps import graph_of, pool_of, rows_of, variant_for
from app.errors import AppError
from app.schema.labels import ACTIVE_FINDING_STATES, CUR, VALID_TO_OPEN
from app.tools.base import Projector
from app.tools.cypher import unique_comprehension_vars
from app.tools.t03.find_entities import fulltext_term

router = APIRouter(tags=["keps"])

OPEN_STATES = list(ACTIVE_FINDING_STATES)

CARD = """k.key AS key, k.number AS number, k.title AS title, k.owning_sig AS owning_sig, k.status AS status,
 k.stage AS stage, k.latest_milestone AS latest_milestone, k.url AS url,
 size([(f:Finding)-[:ABOUT]->(k) WHERE f.state IN $open_states | f]) AS open_findings"""


def _list_template(limit: int) -> str:
    return f"""
MATCH (k:KEP)
WHERE ($sig = '' OR k.owning_sig = $sig) AND ($status = '' OR k.status = $status)
RETURN {CARD}
ORDER BY k.number, k.key
LIMIT {limit}
"""


def _search_template(limit: int) -> str:
    return f"""
CALL db.idx.fulltext.queryNodes('KEP', $term) YIELD node AS k, score
WHERE ($sig = '' OR k.owning_sig = $sig) AND ($status = '' OR k.status = $status)
RETURN {CARD}
ORDER BY score DESC, k.key
LIMIT {limit}
"""


LIMITS = (10, 20, 50, 100, 300)
LIST = {n: _list_template(n) for n in LIMITS}
SEARCH = {n: _search_template(n) for n in LIMITS}

BY_NUMBER = f"""
MATCH (k:KEP {{number: $number}})
RETURN {CARD}
ORDER BY k.key
LIMIT 10
"""

BY_PATH_CARD = f"""
MATCH (k:KEP {{key: $key}})
RETURN {CARD}
LIMIT 1
"""

DETAIL = unique_comprehension_vars(f"""
MATCH (k:KEP {{key: $key}})
RETURN k.summary AS summary, k.sig_dir AS sig_dir, k.creation_date AS creation_date,
 k.last_updated AS last_updated,
 {{alpha: k.milestone_alpha, beta: k.milestone_beta, stable: k.milestone_stable,
   deprecated: k.milestone_deprecated, disabled: k.milestone_disabled, removed: k.milestone_removed}} AS milestones,
 [(p:Person)-[r:AUTHORED]->(k) WHERE {CUR} | {{login: p.login, url: p.url}}] AS authors,
 [(p:Person)-[r:REVIEWS]->(k) WHERE {CUR} | {{login: p.login, url: p.url}}] AS reviewers,
 [(p:Person)-[r:APPROVES]->(k) WHERE {CUR} | {{login: p.login, url: p.url}}] AS approvers,
 [(p:Person)-[r:PRR_APPROVED]->(k) WHERE {CUR} | {{login: p.login, stage: r.stage, url: p.url}}] AS prr_approvers,
 [(k)-[r:GATED_BY]->(g:FeatureGate) WHERE {CUR} | g.name] AS feature_gates,
 [(s)-[r:PARTICIPATES]->(k) WHERE {CUR} | s.key] AS participating_sigs,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE {CUR} | {{key: i.key, number: i.number, state: i.state,
   state_reason: i.state_reason, closed_at_iso: i.closed_at_iso, labels: i.labels_current,
   milestone: i.milestone_current, url: i.url}}] AS tracking_issue,
 [(k)-[r:REPLACES]->(o:KEP) WHERE {CUR} | {{key: o.key, number: o.number, title: o.title, status: o.status,
   url: o.url, declared_by: r.declared_by}}] AS replaces,
 [(o:KEP)-[r:REPLACES]->(k) WHERE {CUR} | {{key: o.key, number: o.number, title: o.title, status: o.status,
   url: o.url, declared_by: r.declared_by}}] AS replaced_by,
 [(k)-[r:SEE_ALSO]->(o:KEP) WHERE {CUR} | {{key: o.key, number: o.number, title: o.title, status: o.status,
   url: o.url}}] AS see_also,
 [(k)-[:HAS_DOCUMENT]->(:Document)-[:HAS_SECTION]->(s:Section) | {{anchor: s.anchor, heading: s.heading,
   kind: s.kind, url: s.url, order: s.order}}] AS sections,
 coalesce(k.source_url, k.url) AS source_url
LIMIT 1
""")

FINDING_FIELDS = """f.key AS key, f.kind AS kind, f.kep_path AS kep_path, k.number AS kep_number, k.title AS kep_title,
 k.owning_sig AS owning_sig, f.state AS state, f.a_label AS a_label, f.a_value AS a_value, f.a_url AS a_url,
 f.b_label AS b_label, f.b_value AS b_value, f.b_url AS b_url, f.suggested_fix AS suggested_fix,
 f.detected_at_iso AS detected_at_iso, f.triage_verdict AS triage_verdict, f.assessment AS assessment"""

KEP_FINDINGS = f"""
MATCH (f:Finding)-[:ABOUT]->(k:KEP {{key: $key}})
RETURN {FINDING_FIELDS}
ORDER BY f.kind, f.key
LIMIT 50
"""

HISTORY = """
MATCH (c:StatusChange {kep_path: $key})
OPTIONAL MATCH (c)-[:IN_COMMIT]->(:Commit)-[:IN_PR]->(pr:PullRequest)
WITH c, collect(pr)[0] AS pr
RETURN c.key AS key, c.kind AS kind, c.field AS field, c.op AS op, c.from_value AS from_value,
 c.to_value AS to_value, c.at_iso AS at_iso, c.actor_login AS actor_login, c.is_reversal AS is_reversal,
 c.source_url AS source_url, c.commit_sha AS commit_sha,
 CASE WHEN pr IS NULL THEN NULL ELSE {number: pr.number, url: pr.url} END AS pr
ORDER BY c.at, c.seq, c.key
LIMIT 500
"""

DECISIONS = unique_comprehension_vars("""
MATCH (d:Decision {kep_path: $key})
RETURN d.key AS key, d.kind AS kind, d.summary AS summary, d.decided_at_iso AS decided_at_iso,
 d.human_decider AS human_decider,
 [(d)-[r:DECIDED_BY]->(p:Person) | {login: p.login, role: r.role, url: p.url}] AS deciders,
 [(d)-[:EVIDENCED_BY]->(e) | e] AS evidence
ORDER BY d.decided_at, d.key
LIMIT 200
""")


def _card(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in ("key", "number", "title", "owning_sig", "status", "stage", "latest_milestone",
                                     "url", "open_findings")}  # fmt: skip


async def resolve_card(request: Request, number: int, path: str | None) -> dict[str, Any]:
    pool = pool_of(request)
    if path:
        out = await pool.ro_query(graph_of(request), BY_PATH_CARD, {"key": path.strip("/"), "open_states": OPEN_STATES})
        rows = rows_of(out)
        if not rows or rows[0]["number"] not in (number, None):
            raise AppError("kep_not_found", {"number": number, "path": path})
        return _card(rows[0])
    rows = rows_of(await pool.ro_query(graph_of(request), BY_NUMBER, {"number": number, "open_states": OPEN_STATES}))
    if not rows:
        raise AppError("kep_not_found", {"number": number})
    if len(rows) > 1:
        raise AppError("ambiguous_reference", {"candidates": [_card(r) for r in rows]})
    return _card(rows[0])


@router.get("/keps")
async def list_keps(
    request: Request,
    q: str = Query(default="", max_length=200),
    sig: str = Query(default="", max_length=60),
    status: str = Query(default="", max_length=30),
    limit: int = Query(default=20, ge=1, le=300),
) -> dict[str, Any]:
    pool = pool_of(request)
    variant = variant_for(limit, LIMITS)
    args: dict[str, Any] = {"sig": sig, "status": status, "open_states": OPEN_STATES}
    q = q.strip()
    num = q.upper().removeprefix("KEP-").removeprefix("KEP").strip()
    if num.isdigit():
        rows = rows_of(await pool.ro_query(graph_of(request), BY_NUMBER, {**args, "number": int(num)}))
    elif q:
        term = fulltext_term(q)
        rows = rows_of(await pool.ro_query(graph_of(request), SEARCH[variant], {**args, "term": term})) if term else []
    else:
        rows = rows_of(await pool.ro_query(graph_of(request), LIST[variant], args))
    return {"items": [_card(r) for r in rows[:limit]]}


@router.get("/keps/{number}")
async def get_kep_detail(request: Request, number: int, path: str | None = Query(default=None)) -> dict[str, Any]:
    card = await resolve_card(request, number, path)
    pool = pool_of(request)
    detail = rows_of(await pool.ro_query(graph_of(request), DETAIL, {"key": card["key"], "open": VALID_TO_OPEN}))[0]
    findings = rows_of(await pool.ro_query(graph_of(request), KEP_FINDINGS, {"key": card["key"]}))
    with_verdicts(findings, load_verdicts())
    issues = detail.pop("tracking_issue") or []
    sections = sorted(detail.pop("sections") or [], key=lambda s: (s.get("order") or 0, s.get("anchor") or ""))
    return _detail_out(card, detail, issues, findings, sections)


def _detail_out(
    card: dict[str, Any],
    detail: dict[str, Any],
    issues: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    out = {**card, **{k: v for k, v in detail.items() if k not in ("replaces", "replaced_by", "see_also")}}
    out["tracking_issue"] = issues[0] if issues else None
    out["relations"] = {k: detail.get(k) or [] for k in ("replaces", "replaced_by", "see_also")}
    out["findings"] = findings
    out["sections"] = [{k: s.get(k) for k in ("anchor", "heading", "kind", "url")} for s in sections]
    return out


@router.get("/keps/{number}/history")
async def kep_history(request: Request, number: int, path: str | None = Query(default=None)) -> dict[str, Any]:
    card = await resolve_card(request, number, path)
    rows = rows_of(await pool_of(request).ro_query(graph_of(request), HISTORY, {"key": card["key"]}))
    return {"items": rows}


@router.get("/keps/{number}/decisions")
async def kep_decisions(request: Request, number: int, path: str | None = Query(default=None)) -> dict[str, Any]:
    card = await resolve_card(request, number, path)
    out = await pool_of(request).ro_query(graph_of(request), DECISIONS, {"key": card["key"]})
    items = []
    for row in out.as_dicts():
        proj = Projector()
        proj.value(row.pop("evidence") or [])
        row["evidence"] = [e.model_dump() for e in proj.evidence.values()]
        items.append(row)
    return {"items": items}
