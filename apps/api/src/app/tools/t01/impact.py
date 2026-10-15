"""`impact_of_change`: the multi-hop blast radius of a KEP, grouped by hop.

Hop structure (each reached node keeps its shortest path from the KEP):
- KEPs and feature gates reached over REPLACES, SUPERSEDED_BY, SEE_ALSO (either
  direction) and GATED_BY (two KEPs that share a gate are 2 hops apart);
  intermediate nodes are KEPs or feature gates only, so SIG, person and
  release hubs never fan the search out; template placeholder gates
  (MyFeature, TBD) are listed but never link two KEPs.
- For every KEP reached before the last hop: its owning SIG (OWNED_BY), its
  current authors and approvers (AUTHORED, APPROVES) and its tracking issue
  when that issue is open (TRACKED_BY), one hop further.
Open pull requests are not reported: the graph holds merged pull requests
(and unfetched stubs) only.
"""

from __future__ import annotations

from typing import Any, Literal

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

LINK_TYPES = ("REPLACES", "SUPERSEDED_BY", "SEE_ALSO", "GATED_BY")
REACH_LIMIT = 150
# Gate names from the KEP template that some kep.yaml files still carry; listed when declared,
# never used to link two KEPs.
PLACEHOLDER_GATES = ["MyFeature", "TBD"]


def _reach_template(depth: int) -> str:
    rels = "|".join(LINK_TYPES)
    return f"""
MATCH (k:KEP {{key: $key}})
MATCH path = (k)-[:{rels}*1..{depth}]-(n)
WHERE n <> k AND (n:KEP OR n:FeatureGate)
  AND all(x IN nodes(path)[1..-1] WHERE x <> k AND (x:KEP OR (x:FeatureGate AND NOT x.key IN $placeholders)))
WITH n, path ORDER BY length(path), [x IN nodes(path) | x.key]
WITH n, collect(path)[0] AS path
RETURN n AS node, length(path) AS hop, path
ORDER BY hop, n.key
LIMIT {REACH_LIMIT}
"""


REACH = {d: _reach_template(d) for d in (2, 3)}

ATTACH = """
UNWIND $keys AS kk
MATCH (k:KEP {key: kk})
RETURN k.key AS kep,
 [(k)-[r:OWNED_BY]->(s:SIG) WHERE coalesce(r.valid_to, $open) = $open | s] AS sigs,
 [(p:Person)-[r:AUTHORED]->(k) WHERE coalesce(r.valid_to, $open) = $open AND coalesce(p.is_bot, false) = false
   | p] AS authors,
 [(p:Person)-[r:APPROVES]->(k) WHERE coalesce(r.valid_to, $open) = $open AND coalesce(p.is_bot, false) = false
   | p] AS approvers,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE coalesce(r.valid_to, $open) = $open AND i.state = 'open' | i] AS open_issues
LIMIT 200
"""

_GROUPS = {"KEP": "keps", "FeatureGate": "feature_gates", "SIG": "sigs", "Person": "people", "Issue": "open_issues"}


class ImpactParams(ToolParams):
    kep_ref: KepRef
    depth: Literal[2, 3] = 2


class ImpactOfChange(Tool):
    name = "impact_of_change"
    description = (
        "Blast radius of changing a KEP, grouped by hop (depth 2 or 3): KEPs that replace / are replaced by it "
        "or SEE_ALSO it, KEPs sharing a feature gate, and for each KEP reached its owning SIG, current authors "
        "and approvers and its open tracking issue. Every node comes with its shortest path from the KEP "
        "(paths). Open pull requests are not in the graph (merged PRs only)."
    )
    Params = ImpactParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: ImpactParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        root = res.key
        reached = await run.query(REACH[p.depth], {"key": root, "placeholders": PLACEHOLDER_GATES}, limit=REACH_LIMIT)

        hop_of: dict[str, int] = {root: 0}
        kep_keys = {root}
        path_of: dict[str, list[str]] = {root: [root]}
        groups: dict[int, dict[str, list[dict[str, Any]]]] = {}

        def place(node: dict[str, Any], hop: int, path: list[str]) -> None:
            key = node["key"]
            if not key or key in hop_of:
                return
            hop_of[key] = hop
            path_of[key] = path
            bucket = groups.setdefault(hop, {g: [] for g in _GROUPS.values()})
            bucket[_GROUPS[node["label"]]].append(node)
            if node["label"] == "KEP":
                kep_keys.add(key)

        for row in reached:
            place(row["node"], int(row["hop"]), row["path"])

        keps = [k for k in kep_keys if hop_of[k] < p.depth]
        attached = await run.query(ATTACH, {"keys": keps}, limit=200)
        for row in sorted(attached, key=lambda r: (hop_of[r["kep"]], r["kep"])):
            base_hop = hop_of[row["kep"]]
            base_path = path_of[row["kep"]]
            for field, rel in (("sigs", "OWNED_BY"), ("authors", "AUTHORED"), ("approvers", "APPROVES"),
                               ("open_issues", "TRACKED_BY")):  # fmt: skip
                for node in row.get(field, []):
                    place(node, base_hop + 1, [*base_path, rel, node["key"]])

        for key, path in path_of.items():
            if key != root:
                run.paths.append(path)
        rows: list[dict[str, Any]] = [
            {
                "kep": res.candidates[0],
                "depth": p.depth,
                "reached": len(hop_of) - 1,
                "by_hop": {str(h): {g: len(v) for g, v in b.items() if v} for h, b in sorted(groups.items())},
                "open_pull_requests": "not in graph (merged pull requests only)",
            }
        ]
        for hop, bucket in sorted(groups.items()):
            rows.append({"hop": hop, **{g: v for g, v in bucket.items() if v}})
        return run.result(rows)
