"""Tools 21 `path_between` and 23 `rank_people` (03 §15.2)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator

from app.errors import AppError
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import _coerce, resolve_kep, unresolved_rows

EndpointLabel = Literal["KEP", "Person", "SIG", "FeatureGate", "Issue", "PullRequest", "Decision", "Release"]

# Relationship allow-list for path search: no derived, text-mention or bot-dominated
# types, and no Release/Label hubs (03 §15.2 tool 21).
PATH_REL_TYPES = (
    "AUTHORED", "REVIEWS", "APPROVES", "PRR_APPROVED", "OWNED_BY", "PARTICIPATES", "CHAIRS", "TECH_LEAD",
    "REPLACES", "SUPERSEDED_BY", "SEE_ALSO", "GATED_BY", "TRACKED_BY", "DECIDED_BY", "ABOUT", "EVIDENCED_BY",
    "MERGED", "MEMBER_OF", "APPROVER", "REVIEWER",
)  # fmt: skip


def _path_template(src: str, dst: str, max_len: int, count: int) -> str:
    rels = ", ".join(f"'{t}'" for t in PATH_REL_TYPES)
    return f"""
MATCH (a:{src} {{key: $from_key}}), (b:{dst} {{key: $to_key}})
CALL algo.SPpaths({{sourceNode: a, targetNode: b, relTypes: [{rels}], relDirection: 'both',
  pathCount: {count * 4}, maxLen: {max_len}}}) YIELD path, pathWeight
WITH path, pathWeight
WHERE none(n IN nodes(path) WHERE coalesce(n.is_bot, false) = true)
RETURN path, length(path) AS length,
 [r IN relationships(path) | {{type: type(r), from: startNode(r).key, to: endNode(r).key, stage: r.stage,
   role: r.role}}] AS edges
ORDER BY pathWeight, length, [n IN nodes(path) | n.key]
LIMIT {count}
"""


class PathBetweenParams(ToolParams):
    from_label: EndpointLabel
    from_key: str = Field(min_length=1, max_length=300, description="Node key; for KEP a number or path")
    to_label: EndpointLabel
    to_key: str = Field(min_length=1, max_length=300, description="Node key; for KEP a number or path")
    max_len: Literal[2, 3, 4] = 4
    path_count: Literal[1, 3] = 3

    @field_validator("from_key", "to_key")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip().lstrip("@")


class PathBetween(Tool):
    name = "path_between"
    description = (
        "Shortest explainable connections (up to 4 hops, algo.SPpaths, both directions) between two entities, "
        "e.g. a person (Person, key = GitHub login) and a KEP (key = number or path). Paths avoid bots, release "
        "and label hubs. Each path lists nodes and typed edges (e.g. PRR_APPROVED with stage). Length 1 = direct "
        "involvement. Use for 'how is X connected to Y'."
    )
    Params = PathBetweenParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: PathBetweenParams = params
        run = Run(ctx)
        keys: list[str] = []
        for label, key in ((p.from_label, p.from_key), (p.to_label, p.to_key)):
            if label == "KEP":
                ref = _coerce(key)
                res = await resolve_kep(run, ref)
                if res.key is None:
                    return run.result(unresolved_rows(ref, res))
                keys.append(res.key)
            elif label == "Person":
                keys.append(key.lower())
            elif label in ("Issue", "PullRequest") and re.fullmatch(r"#?\d{1,6}", key):
                keys.append(f"kubernetes/enhancements#{key.lstrip('#')}")
            else:
                keys.append(key)
        # Iterative deepening: SPpaths cost grows steeply with maxLen on hub-heavy graphs, so the
        # shortest length is found first and longer searches run only when nothing shorter exists.
        rows: list[dict[str, Any]] = []
        searched = 0
        for max_len in range(2, p.max_len + 1):
            template = _path_template(p.from_label, p.to_label, max_len, p.path_count)
            try:
                rows = await run.query(template, {"from_key": keys[0], "to_key": keys[1]}, limit=p.path_count + 1)
            except AppError as exc:
                if exc.code != "graph_timeout":
                    raise
                return run.result([{"not_connected_within": searched, "from": keys[0], "to": keys[1],
                                    "search_timed_out_at": max_len}])  # fmt: skip
            searched = max_len
            if rows:
                break
        for row in rows:
            if isinstance(row.get("path"), list):
                run.paths.append(row["path"])
        if not rows:
            rows = [{"not_connected_within": p.max_len, "from": keys[0], "to": keys[1]}]
        return run.result(rows)


def _rank_template(order: str, limit: int) -> str:
    return f"""
MATCH (p:Person)-[r:APPROVES|REVIEWS|AUTHORED|PRR_APPROVED]->(k:KEP)
WHERE coalesce(r.valid_to, $open) = $open AND coalesce(p.is_bot, false) = false
  AND ($sig = '' OR k.owning_sig = $sig) AND (size($keys) = 0 OR k.key IN $keys)
WITH p, count(DISTINCT k) AS keps, collect(DISTINCT type(r)) AS roles, collect(DISTINCT k.owning_sig) AS sigs
RETURN p AS person, keps, roles, sigs, p.pagerank AS pagerank, p.betweenness AS betweenness
ORDER BY {order}, p.key
LIMIT {limit}
"""


_ORDERS = {
    "pagerank": "coalesce(p.pagerank, -1.0) DESC, keps DESC",
    "betweenness": "coalesce(p.betweenness, -1.0) DESC, keps DESC",
    "degree": "keps DESC",
}
RANK = {(m, n): _rank_template(o, n) for m, o in _ORDERS.items() for n in (5, 10, 20)}
HAS_METRIC = "MATCH (p:Person) WHERE p.{metric} IS NOT NULL RETURN count(p) AS n"


class RankPeopleParams(ToolParams):
    sig: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,60}$")
    kep_refs: list[str] = Field(default_factory=list, max_length=20)
    metric: Literal["pagerank", "betweenness", "degree"] = "pagerank"
    limit: Literal[5, 10, 20] = 10

    @field_validator("kep_refs")
    @classmethod
    def _refs(cls, v: list[str]) -> list[str]:
        return [_coerce(x) for x in v]


class RankPeople(Tool):
    name = "rank_people"
    description = (
        "Who is most central in a SIG or a set of KEPs: people with author/reviewer/approver/PRR-approver edges "
        "into the scope, ordered by stored PageRank or betweenness when the analytics run has computed them, "
        "else by degree (number of distinct KEPs). metric_used says which ordering applied."
    )
    Params = RankPeopleParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: RankPeopleParams = params
        run = Run(ctx)
        keys: list[str] = []
        for ref in p.kep_refs:
            res = await resolve_kep(run, ref)
            if res.key is None:
                return run.result(unresolved_rows(ref, res))
            keys.append(res.key)
        metric = p.metric
        if metric != "degree":
            present = await run.query(HAS_METRIC.format(metric=metric), limit=2)
            if not present or not present[0].get("n"):
                metric = "degree"
        rows = await run.query(RANK[(metric, p.limit)], {"sig": p.sig or "", "keys": keys}, limit=p.limit)
        return run.result([{"metric_requested": p.metric, "metric_used": metric}, *rows])
