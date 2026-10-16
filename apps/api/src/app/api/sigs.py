"""SIG list and SIG page: leadership, owned KEPs, people and findings.

A KEP belongs to the SIG named by its `owning_sig` (the same field `/v1/keps?sig=`
and `/v1/findings?sig=` filter on). Leadership comes from current `sigs.yaml`
edges. `subprojects` lists `Subproject` nodes linked by `HAS_SUBPROJECT`; it is
empty while the ingest does not load subprojects.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Request

from app.api.audit_check import load_verdicts, with_verdicts
from app.api.deps import graph_of, pool_of, rows_of
from app.api.keps import CARD, FINDING_FIELDS, OPEN_STATES, _card
from app.db.falkordb import FalkorPool
from app.errors import AppError
from app.schema.labels import CUR, LEAD_ROLE_NAMES, VALID_TO_OPEN
from app.tools.cypher import unique_comprehension_vars

router = APIRouter(tags=["sigs"])

SIG_ROLES = LEAD_ROLE_NAMES
KEP_ROLES = {"AUTHORED": "author", "REVIEWS": "reviewer", "APPROVES": "approver", "PRR_APPROVED": "prr_approver"}
ROLE_ORDER = [*SIG_ROLES.values(), *KEP_ROLES.values()]

ITEM = f"""s.key AS key, s.display_name AS display_name, s.mission AS mission,
 coalesce(s.in_scope, false) AS in_scope, s.url AS url,
 [(p:Person)-[r:CHAIRS]->(s) WHERE {CUR} | {{login: p.login, url: p.url}}] AS chairs,
 [(p:Person)-[r:TECH_LEAD]->(s) WHERE {CUR} | {{login: p.login, url: p.url}}] AS tech_leads"""

LIST = unique_comprehension_vars(f"""
MATCH (s:SIG)
RETURN {ITEM}
ORDER BY in_scope DESC, key
""")

ONE = unique_comprehension_vars(f"""
MATCH (s:SIG {{key: $key}})
RETURN {ITEM},
 [(s)-[:HAS_SUBPROJECT]->(sp:Subproject) | {{name: coalesce(sp.name, sp.key), url: coalesce(sp.url, sp.source_url)}}]
   AS subprojects
LIMIT 1
""")

KEP_COUNTS = """
MATCH (k:KEP)
WHERE $key = '' OR k.owning_sig = $key
RETURN k.owning_sig AS sig, count(k) AS keps,
 sum(size([(f:Finding)-[:ABOUT]->(k) WHERE f.state IN $open_states | f])) AS open_findings
"""

KEPS = f"""
MATCH (k:KEP {{owning_sig: $key}})
RETURN {CARD}
ORDER BY k.number, k.key
"""

LEADERS = f"""
MATCH (p:Person)-[r:CHAIRS|TECH_LEAD|EMERITUS_LEAD|LIAISON|SUBPROJECT_LEAD]->(s:SIG {{key: $key}})
WHERE {CUR}
RETURN p.login AS login, p.url AS url, type(r) AS rel
"""

CONTRIBUTORS = f"""
MATCH (p:Person)-[r:AUTHORED|REVIEWS|APPROVES|PRR_APPROVED]->(k:KEP {{owning_sig: $key}})
WHERE {CUR} AND coalesce(p.is_bot, false) = false
RETURN p.login AS login, p.url AS url, type(r) AS rel, count(DISTINCT k) AS keps
"""

FINDINGS = f"""
MATCH (f:Finding)-[:ABOUT]->(k:KEP {{owning_sig: $key}})
RETURN {FINDING_FIELDS}
ORDER BY f.kind, f.kep_path, f.key
LIMIT 500
"""


def _people(leaders: list[dict[str, Any]], contributors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Leaders first, then by the number of SIG KEPs a person is on; roles in a fixed order."""
    people: dict[str, dict[str, Any]] = {}
    weight: Counter[str] = Counter()
    for row in leaders:
        p = people.setdefault(row["login"], {"login": row["login"], "url": row["url"], "roles": set()})
        p["roles"].add(SIG_ROLES[row["rel"]])
    for row in contributors:
        p = people.setdefault(row["login"], {"login": row["login"], "url": row["url"], "roles": set()})
        p["roles"].add(KEP_ROLES[row["rel"]])
        weight[row["login"]] = max(weight[row["login"]], int(row["keps"]))
    ordered = sorted(
        people.values(),
        key=lambda p: (not (p["roles"] & set(SIG_ROLES.values())), -weight[p["login"]], p["login"]),
    )
    return [{**p, "roles": [r for r in ROLE_ORDER if r in p["roles"]]} for p in ordered]


def _item(row: dict[str, Any], counts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    c = counts.get(row["key"], {})
    return {
        **{k: row[k] for k in ("key", "display_name", "mission", "in_scope", "url")},
        "keps": int(c.get("keps") or 0),
        "open_findings": int(c.get("open_findings") or 0),
        "chairs": row["chairs"],
        "tech_leads": row["tech_leads"],
    }


async def _kep_counts(pool: FalkorPool, graph: str, key: str) -> dict[str, dict[str, Any]]:
    rows = rows_of(await pool.ro_query(graph, KEP_COUNTS, {"key": key, "open_states": OPEN_STATES}))
    return {r["sig"]: r for r in rows if r["sig"]}


@router.get("/sigs")
async def list_sigs(request: Request) -> dict[str, Any]:
    pool, graph = pool_of(request), graph_of(request)
    rows = rows_of(await pool.ro_query(graph, LIST, {"open": VALID_TO_OPEN}))
    counts = await _kep_counts(pool, graph, "")
    return {"items": [_item(r, counts) for r in rows]}


@router.get("/sigs/{key}")
async def get_sig(request: Request, key: str) -> dict[str, Any]:
    pool, graph = pool_of(request), graph_of(request)
    sig = key.strip().lower()
    args: dict[str, Any] = {"key": sig, "open": VALID_TO_OPEN, "open_states": OPEN_STATES}
    rows = rows_of(await pool.ro_query(graph, ONE, args))
    if not rows:
        raise AppError("not_found", {"sig": key[:100]})
    item = _item(rows[0], await _kep_counts(pool, graph, sig))
    keps = [_card(r) for r in rows_of(await pool.ro_query(graph, KEPS, args))]
    leaders = rows_of(await pool.ro_query(graph, LEADERS, args))
    contributors = rows_of(await pool.ro_query(graph, CONTRIBUTORS, args))
    findings = with_verdicts(rows_of(await pool.ro_query(graph, FINDINGS, args)), load_verdicts())
    return {
        **item,
        "subprojects": sorted(rows[0]["subprojects"] or [], key=lambda s: s["name"] or ""),
        "keps_by_status": dict(sorted(Counter(k["status"] or "unknown" for k in keps).items())),
        "keps": keps,
        "people": _people(leaders, contributors),
        "findings": findings,
    }
