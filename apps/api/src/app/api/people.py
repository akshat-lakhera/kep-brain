"""Person page: leadership roles, KEP involvement, decisions, OWNERS entries and connectivity (05 §4.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import graph_of, pool_of, rows_of
from app.api.keps import CARD, OPEN_STATES, _card
from app.errors import AppError
from app.schema.labels import VALID_TO_OPEN

router = APIRouter(tags=["people"])

CUR = "coalesce(r.valid_to, $open) = $open"
ROLE_NAMES = {
    "CHAIRS": "chair",
    "TECH_LEAD": "tech_lead",
    "EMERITUS_LEAD": "emeritus_lead",
    "LIAISON": "liaison",
    "SUBPROJECT_LEAD": "subproject_lead",
}
ORG_KINDS = ("SIG", "WorkingGroup", "Committee", "Subproject")
KEP_RELS = {"AUTHORED": "authored", "REVIEWS": "reviews", "APPROVES": "approves"}
OWNERS_ROLES = {"APPROVER": "approver", "REVIEWER": "reviewer", "EMERITUS_APPROVER": "emeritus_approver"}
# Display order when one person holds several roles on one decision.
DECISION_ROLE_ORDER = ("author", "approver", "prr_approver", "approve_command", "lgtm", "merger", "actor")
DECISION_LIMIT = 100
CONNECTIVITY_METHOD = (
    "algo.pageRank(null, 'DECIDED_BY') over the whole graph: PageRank on Decision -> Person edges "
    "(a person's weighted share of all derived decisions); rank among people who are not bots"
)

PERSON = "MATCH (p:Person {key: $key}) RETURN p.login AS login, p.url AS url, coalesce(p.is_bot, false) AS is_bot"

ROLES = f"""
MATCH (p:Person {{key: $key}})-[r:CHAIRS|TECH_LEAD|EMERITUS_LEAD|LIAISON|SUBPROJECT_LEAD]->(o)
WHERE {CUR}
RETURN o.key AS org, labels(o) AS labels, type(r) AS rel, r.valid_from_iso AS valid_from_iso,
 coalesce(r.source_url, o.source_url) AS source_url
ORDER BY o.key, rel
"""

KEPS = f"""
MATCH (p:Person {{key: $key}})-[r:AUTHORED|REVIEWS|APPROVES|PRR_APPROVED]->(k:KEP)
WHERE {CUR}
RETURN type(r) AS rel, r.stage AS prr_stage, {CARD}
ORDER BY k.number, k.key, prr_stage
"""

DECISIONS = f"""
MATCH (d:Decision)-[r:DECIDED_BY]->(p:Person {{key: $key}})
WITH d, collect(DISTINCT r.role) AS roles
OPTIONAL MATCH (k:KEP {{key: d.kep_path}})
RETURN d.key AS key, d.kind AS kind, d.summary AS summary, k.number AS kep_number, k.title AS kep_title,
 roles, d.decided_at_iso AS decided_at_iso, coalesce(d.url, d.source_url) AS url
ORDER BY d.decided_at DESC, d.key
LIMIT {DECISION_LIMIT}
"""

OWNERS = f"""
MATCH (d:Document)-[r:APPROVER|REVIEWER|EMERITUS_APPROVER]->(p:Person {{key: $key}})
WHERE {CUR}
RETURN d.directory AS directory, type(r) AS rel, null AS via_alias, coalesce(d.url, d.source_url) AS source_url
UNION ALL
MATCH (d:Document)-[r:APPROVER|REVIEWER|EMERITUS_APPROVER]->(a:Alias)<-[m:MEMBER_OF]-(p:Person {{key: $key}})
WHERE {CUR} AND coalesce(m.valid_to, $open) = $open
RETURN d.directory AS directory, type(r) AS rel, a.name AS via_alias, coalesce(d.url, d.source_url) AS source_url
"""

CONNECTIVITY = """
MATCH (node:Person)
WHERE node.pagerank IS NOT NULL AND coalesce(node.is_bot, false) = false
WITH collect({k: node.key, s: node.pagerank}) AS people
WITH people, [x IN people WHERE x.k = $key] AS me
WHERE size(me) > 0
RETURN me[0].s AS score, size([x IN people WHERE x.s > me[0].s]) + 1 AS rank, size(people) AS of
"""


def _org_kind(labels: list[str]) -> str:
    return next((label for label in labels if label in ORG_KINDS), labels[0] if labels else "")


def _decision_role(roles: list[str]) -> str:
    known = [r for r in DECISION_ROLE_ORDER if r in roles]
    return ", ".join(known + sorted(r for r in roles if r not in DECISION_ROLE_ORDER))


@router.get("/people/{login}")
async def get_person(request: Request, login: str) -> dict[str, Any]:
    pool, graph = pool_of(request), graph_of(request)
    key = login.strip().lstrip("@").lower()
    person = rows_of(await pool.ro_query(graph, PERSON, {"key": key}))
    if not key or not person:
        raise AppError("not_found", {"login": login[:100]})
    args = {"key": key, "open": VALID_TO_OPEN, "open_states": OPEN_STATES}

    roles = [
        {
            "org": r["org"],
            "org_kind": _org_kind(r["labels"]),
            "role": ROLE_NAMES[r["rel"]],
            "valid_from_iso": r["valid_from_iso"],
            "source_url": r["source_url"],
        }
        for r in rows_of(await pool.ro_query(graph, ROLES, args))
    ]

    keps: dict[str, list[dict[str, Any]]] = {"authored": [], "reviews": [], "approves": [], "prr_approved": []}
    for r in rows_of(await pool.ro_query(graph, KEPS, args)):
        if r["rel"] == "PRR_APPROVED":
            keps["prr_approved"].append({"stage": r["prr_stage"], "kep": _card(r)})
        else:
            keps[KEP_RELS[r["rel"]]].append(_card(r))

    decisions = []
    for r in rows_of(await pool.ro_query(graph, DECISIONS, args)):
        roles_on = r.pop("roles") or []
        decisions.append({**r, "role": _decision_role(roles_on)})

    owners = sorted(
        (
            {"directory": r["directory"], "role": OWNERS_ROLES[r["rel"]], "via_alias": r["via_alias"],
             "source_url": r["source_url"]}
            for r in rows_of(await pool.ro_query(graph, OWNERS, args))
        ),
        key=lambda o: (o["directory"] or "", o["role"], o["via_alias"] or ""),
    )  # fmt: skip

    connectivity = None
    if not person[0]["is_bot"]:
        rank = rows_of(await pool.ro_query(graph, CONNECTIVITY, {"key": key}, timeout_ms=10000))
        if rank and rank[0]["score"] is not None:
            connectivity = {
                "score": round(float(rank[0]["score"]), 8),
                "rank": int(rank[0]["rank"]),
                "of": int(rank[0]["of"]),
                "method": CONNECTIVITY_METHOD,
            }

    return {
        "login": person[0]["login"],
        "url": person[0]["url"],
        "is_bot": bool(person[0]["is_bot"]),
        "roles": roles,
        "keps": keps,
        "decisions": decisions,
        "owners": owners,
        "connectivity": connectivity,
    }
