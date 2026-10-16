"""`path_to_decision`: how a person is connected to the decisions about a KEP.

Shortest first, in three tiers (a later tier runs only when the earlier ones
found nothing):
1. length 1: the person is named on the Decision (Decision -DECIDED_BY {role}-> Person);
2. length 2: the person authored/approved/reviewed/PRR-approved the KEP the
   Decision is ABOUT, or submitted a review / command comment the Decision is
   EVIDENCED_BY;
3. length 3-4: `algo.SPpaths` (both directions, allow-listed edge types, no
   bots) from the person to the KEP, extended by the KEP's ABOUT edge to its
   most recent matching Decision.
`algo.SPpaths` straight to each Decision is not used: from a person with
thousands of DECIDED_BY edges it exceeds the 2 s read budget at length 3.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator

from app.errors import AppError
from app.ingest.common import normalise_login
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows
from app.tools.t03.history import DecisionKind

PERSON = "MATCH (p:Person {key: $login}) RETURN p LIMIT 1"

DIRECT = """
MATCH (d:Decision {kep_path: $key})-[r:DECIDED_BY]->(p:Person {key: $login})
WHERE size($kinds) = 0 OR d.kind IN $kinds
RETURN d AS decision, collect(r.role) AS roles
ORDER BY d.decided_at DESC, d.key
LIMIT 50
"""

VIA_KEP = """
MATCH (p:Person {key: $login})-[r:AUTHORED|APPROVES|REVIEWS|PRR_APPROVED]->(k:KEP {key: $key})
WITH p, k, collect(DISTINCT type(r)) AS rels
MATCH (d:Decision)-[:ABOUT]->(k)
WHERE size($kinds) = 0 OR d.kind IN $kinds
RETURN d AS decision, rels
ORDER BY d.decided_at DESC, d.key
LIMIT 50
"""

VIA_EVIDENCE = """
MATCH (p:Person {key: $login})-[r:SUBMITTED|COMMENTED]->(x)<-[e:EVIDENCED_BY]-(d:Decision {kep_path: $key})
WHERE size($kinds) = 0 OR d.kind IN $kinds
RETURN d AS decision, type(r) AS rel, x AS via, e.evidence_kind AS evidence_kind
ORDER BY d.decided_at DESC, d.key, x.key
LIMIT 50
"""

LATEST_DECISION = """
MATCH (d:Decision {kep_path: $key})
WHERE size($kinds) = 0 OR d.kind IN $kinds
RETURN d AS decision
ORDER BY d.decided_at DESC, d.key
LIMIT 1
"""

SP_REL_TYPES = (
    "AUTHORED", "REVIEWS", "APPROVES", "PRR_APPROVED", "REPLACES", "SUPERSEDED_BY", "SEE_ALSO", "GATED_BY",
    "OWNED_BY", "PARTICIPATES", "CHAIRS", "TECH_LEAD",
)  # fmt: skip


def _sp_template(max_len: int) -> str:
    rels = ", ".join(f"'{t}'" for t in SP_REL_TYPES)
    return f"""
MATCH (a:Person {{key: $login}}), (b:KEP {{key: $key}})
CALL algo.SPpaths({{sourceNode: a, targetNode: b, relTypes: [{rels}], relDirection: 'both',
  pathCount: 24, maxLen: {max_len}}}) YIELD path, pathWeight
WITH path, pathWeight
WHERE none(n IN nodes(path) WHERE coalesce(n.is_bot, false) = true)
RETURN path, [r IN relationships(path) | type(r)] AS edge_types
ORDER BY pathWeight, [n IN nodes(path) | n.key]
LIMIT 12
"""


SP = {n: _sp_template(n) for n in (2, 3)}


class PathToDecisionParams(ToolParams):
    person: str = Field(min_length=1, max_length=60, description="GitHub login, e.g. sanposhiho")
    kep_ref: KepRef
    kinds: list[DecisionKind] = Field(default_factory=list, description="Decision kinds; empty means all")
    path_count: Literal[1, 3, 5] = 3

    @field_validator("person")
    @classmethod
    def _login(cls, v: str) -> str:
        v = normalise_login(v) or ""
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.\-\[\]]{0,59}", v):
            raise ValueError("person must be a GitHub login")
        return v


class PathToDecision(Tool):
    name = "path_to_decision"
    description = (
        "Shortest explainable path from a person (GitHub login) to the decisions about a KEP: named on the "
        "Decision (length 1, with role), or via the KEP / the review or comment that evidences it (length 2), "
        "else algo.SPpaths person→KEP plus ABOUT (length 3-4). Each row is a path with its edge types."
    )
    Params = PathToDecisionParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: PathToDecisionParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        key = res.key
        person = await run.query(PERSON, {"login": p.person}, limit=2)
        if not person:
            return run.result([{"person_not_found": p.person}])
        args = {"login": p.person, "key": key, "kinds": list(p.kinds)}
        rows: list[dict[str, Any]] = []

        for row in await run.query(DIRECT, args, limit=50):
            d = row["decision"]
            rows.append(_row(d, [p.person, "DECIDED_BY", d["key"]], ["DECIDED_BY"], roles=row["roles"]))
        if not rows:
            for row in await run.query(VIA_KEP, args, limit=50):
                d = row["decision"]
                rel = row["rels"][0]
                rows.append(_row(d, [p.person, rel, key, "ABOUT", d["key"]], [rel, "ABOUT"], via_rels=row["rels"]))
            seen: set[str] = {r["decision"]["key"] for r in rows}
            for row in await run.query(VIA_EVIDENCE, args, limit=50):
                d = row["decision"]
                if d["key"] in seen:
                    continue
                seen.add(d["key"])
                rel, via = row["rel"], row["via"]
                rows.append(_row(d, [p.person, rel, via["key"], "EVIDENCED_BY", d["key"]], [rel, "EVIDENCED_BY"],
                                 via=via, evidence_kind=row.get("evidence_kind")))  # fmt: skip
            rows.sort(key=lambda r: str(r["decision"].get("decided_at_iso", "")), reverse=True)
            rows.sort(key=lambda r: int(r["length"]))
        if not rows:
            rows = await self._via_search(run, args)
        run.truncated = len(rows) > p.path_count
        rows = rows[: p.path_count]
        for r in rows:
            run.paths.append(r["path"])
        if not rows:
            rows = [{"not_connected_within": 4, "person": p.person, "kep": key}]
        return run.result(rows)

    async def _via_search(self, run: Run, args: dict[str, Any]) -> list[dict[str, Any]]:
        latest = await run.query(LATEST_DECISION, args, limit=2)
        if not latest:
            return [{"no_decisions": args["key"], "kinds": args["kinds"]}]
        d = latest[0]["decision"]
        for max_len in (2, 3):
            try:
                found = await run.query(SP[max_len], {"login": args["login"], "key": args["key"]}, limit=13)
            except AppError as exc:
                if exc.code != "graph_timeout":
                    raise
                return []
            unique = {tuple(f["path"]): f for f in found}  # SPpaths may yield the same path twice
            if unique:
                return [_row(d, [*f["path"], "ABOUT", d["key"]], [*f["edge_types"], "ABOUT"]) for f in unique.values()]
        return []


def _row(decision: dict[str, Any], path: list[str], edge_types: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "length": len(edge_types),
        "path": path,
        "edge_types": edge_types,
        "decision": decision,
        **{k: v for k, v in extra.items() if v is not None},
    }
